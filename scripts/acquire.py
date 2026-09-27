"""HalterCheck — coletor interativo v0.3.0.
Salve em scripts/acquire.py. Requer numpy e matplotlib para o gráfico.
USB pode alimentar os halteres; dados continuam chegando por Wi-Fi/TCP.
Formato recebido preservado: halter_id,seq,t_ms,sensor,ax,ay,az,gx,gy,gz.
"""
import base64
import csv
import json
import math
import os
import re
import select
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = '0.4.0'
ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {(h,s) for h in ('H1','H2') for s in ('A','B')}
FIELDS = ['halter_id','seq','t_ms','sensor','ax','ay','az','gx','gy','gz',
          'connection_id','received_monotonic_ns','received_utc','elapsed_receive_s']
GAP_THRESHOLD_S = 0.25


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, data):
    temporary = path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',encoding='utf-8') as f:
        json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.flush(); os.fsync(f.fileno())
    temporary.replace(path)


def choice(prompt, options, default):
    while True:
        answer = input(f'{prompt} [{default}]: ').strip().lower() or default
        if answer in options:
            return answer
        print('Opções:', ', '.join(options))


def integer(prompt, minimum, maximum, default):
    while True:
        try:
            value = int(input(f'{prompt} [{default}]: ').strip() or default)
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f'Informe um inteiro entre {minimum} e {maximum}.')


def enter_pressed():
    if os.name == 'nt':
        import msvcrt
        while msvcrt.kbhit():
            if msvcrt.getwch() in ('\r','\n'):
                return True
    elif select.select([sys.stdin],[],[],0)[0]:
        if sys.stdin.readline() == '':
            raise EOFError('Terminal encerrado.')
        return True
    return False


class Voice:
    words = ('prepare','subir','descer','finalizar')
    def __init__(self, folder):
        self.paths = {}; self.process = None
        audio = folder/'audio'; audio.mkdir(exist_ok=True)
        if os.name == 'nt':
            exe = shutil.which('powershell.exe')
            if not exe:
                raise RuntimeError('PowerShell não encontrado.')
            commands = ['Add-Type -AssemblyName System.Speech',
                        '$v = New-Object System.Speech.Synthesis.SpeechSynthesizer',
                        '$v.Rate = 1',
                        "$pt = $v.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'pt-*' } | Select-Object -First 1",
                        'if ($pt) { $v.SelectVoice($pt.VoiceInfo.Name) }']
            for word in self.words:
                path = audio/f'{word}.wav'; self.paths[word] = path
                literal = str(path).replace("'", "''")
                commands += [f"$v.SetOutputToWaveFile('{literal}')",f"$v.Speak('{word}')",'$v.SetOutputToNull()']
            commands.append('$v.Dispose()')
            encoded = base64.b64encode('\n'.join(commands).encode('utf-16-le')).decode('ascii')
            subprocess.run([exe,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                           check=True,capture_output=True,timeout=40)
        else:
            mac = sys.platform == 'darwin'
            speaker = shutil.which('say') if mac else shutil.which('espeak-ng') or shutil.which('espeak')
            self.player = shutil.which('afplay') if mac else shutil.which('aplay') or shutil.which('paplay')
            if not speaker or not self.player:
                raise RuntimeError('Linux: instale espeak-ng e aplay/paplay. macOS: say e afplay.')
            for word in self.words:
                path = audio/(word+('.aiff' if mac else '.wav')); self.paths[word] = path
                args = [speaker,'-o',str(path),word] if mac else [speaker,'-v','pt-br','-s','190','-w',str(path),word]
                subprocess.run(args,check=True,capture_output=True,timeout=15)
        if any(not p.is_file() or p.stat().st_size < 44 for p in self.paths.values()):
            raise RuntimeError('Falha ao gerar os arquivos de voz.')

    def silence(self):
        if os.name == 'nt':
            import winsound
            winsound.PlaySound(None,0)
        elif self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=.5)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait()
            self.process = None

    def play(self, word):
        self.silence()
        if os.name == 'nt':
            import winsound
            winsound.PlaySound(str(self.paths[word]),winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            self.process = subprocess.Popen([self.player,str(self.paths[word])],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


class Timeline:
    """Relógio monotônico; nunca emite 'subir' no instante de finalizar."""
    def __init__(self, guided, duration=None, phase_s=2, tail_s=5):
        self.guided = guided; self.duration = duration; self.phase_s = phase_s
        self.exercise_start = 10. if guided else 0.
        self.tail_s = tail_s; self.finish_at = None; self.reason = None
        self.prepared = False; self.last_phase = -1; self.done = False

    def step(self, elapsed, finish_requested=False):
        events = []
        deadline = None if self.duration is None else self.exercise_start+self.duration
        if self.finish_at is None and (finish_requested or (deadline is not None and elapsed >= deadline)):
            # Cinco segundos contam do envio efetivo do comando final.
            self.finish_at = elapsed
            self.reason = 'enter' if finish_requested else 'time_limit'
            events.append(('finalizar', elapsed if finish_requested else deadline))
        if self.finish_at is not None:
            self.done = elapsed >= self.finish_at+self.tail_s
            return events
        if self.guided:
            if not self.prepared and elapsed >= 5:
                self.prepared = True
                if elapsed < self.exercise_start:
                    events.append(('prepare',5.))
            if elapsed >= self.exercise_start:
                phase = int((elapsed-self.exercise_start)//self.phase_s)
                if phase > self.last_phase:
                    if phase > self.last_phase+1:
                        events.append(('skipped_phases', self.exercise_start+(self.last_phase+1)*self.phase_s))
                    self.last_phase = phase
                    events.append(('subir' if phase%2 == 0 else 'descer',self.exercise_start+phase*self.phase_s))
        return events


class Recorder:
    def __init__(self):
        self.lock = threading.Lock(); self.shutdown = threading.Event()
        self.active = False; self.failure = None; self.files = []
        self.latest = {}; self.connection_counter = 0; self.rows = 0; self.invalid = 0
        self.sync_events = []
        self.start_ns = None; self.stop_ns = None

    def new_connection(self):
        with self.lock:
            self.connection_counter += 1
            return self.connection_counter

    def ready(self):
        with self.lock:
            now=time.monotonic()
            return all(now-self.latest.get(key,-math.inf)<1 for key in EXPECTED)

    def start(self, folder):
        with self.lock:
            f=(folder/'imu.csv').open('x',newline='',encoding='utf-8',buffering=1); self.files.append(f)
            self.bad=(folder/'invalid.jsonl').open('x',encoding='utf-8',buffering=1); self.files.append(self.bad)
            self.sync_file=(folder/'sync.jsonl').open('x',encoding='utf-8',buffering=1); self.files.append(self.sync_file)
            for event in self.sync_events:
                self.sync_file.write(json.dumps(event,allow_nan=False)+'\n')
            self.writer=csv.writer(f); self.writer.writerow(FIELDS); f.flush()
            self.start_ns=time.monotonic_ns(); self.started_utc=utc_now(); self.active=True

    def record_sync(self, event):
        with self.lock:
            self.sync_events.append(event)
            if self.active:
                try:
                    self.sync_file.write(json.dumps(event,allow_nan=False)+'\n')
                except OSError as exc:
                    self.failure=str(exc); self.active=False

    def process(self, raw, cid, forced_error=None):
        received=time.monotonic_ns(); utc=utc_now(); parsed=None
        try:
            if forced_error:
                raise ValueError(forced_error)
            p=raw.decode('utf-8').strip().split(',')
            if len(p)!=10 or (p[0],p[3]) not in EXPECTED:
                raise ValueError('Formato ou identificador inválido.')
            seq,stamp=int(p[1]),int(p[2]); values=list(map(int,p[4:]))
            if not (0<=seq<=0xFFFFFFFF and 0<=stamp<2**63) or any(not -32768<=v<=32767 for v in values):
                raise ValueError('Valor fora do intervalo.')
            parsed=[p[0],seq,stamp,p[3],*values]
        except (ValueError,UnicodeError) as exc:
            error=str(exc)
        with self.lock:
            if parsed:
                self.latest[(parsed[0],parsed[3])]=time.monotonic()
            if not self.active or received<self.start_ns:
                return
            try:
                if parsed:
                    self.writer.writerow([*parsed,cid,received,utc,(received-self.start_ns)/1e9]); self.rows+=1
                else:
                    self.bad.write(json.dumps(dict(connection_id=cid,received_utc=utc,received_monotonic_ns=received,error=error,raw_hex=raw.hex()))+'\n');self.invalid+=1
            except OSError as exc:
                self.failure=str(exc);self.active=False

    def stop(self):
        with self.lock:
            self.active=False; self.stop_ns=time.monotonic_ns()
            for f in self.files:
                try:
                    f.flush();os.fsync(f.fileno())
                except OSError as exc:
                    self.failure=str(exc)
                finally:
                    try:
                        f.close()
                    except OSError as exc:
                        self.failure=str(exc)
            self.files=[]

    def status(self):
        with self.lock:
            now=time.monotonic()
            text=[]
            for h in ('H1','H2'):
                age=max(now-self.latest.get((h,s),-math.inf) for s in ('A','B'))
                text.append(f'{h}: ativo' if age<GAP_THRESHOLD_S else f'{h}: SEM DADOS RECENTES ({age:.1f}s)')
            return self.rows,' | '.join(text)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        rec=self.server.recorder; cid=rec.new_connection();self.request.settimeout(.25);buf=b''
        pending={}
        while not rec.shutdown.is_set():
            try:
                data=self.request.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf+=data
            while b'\n' in buf:
                raw,buf=buf.split(b'\n',1)
                received_us=time.monotonic_ns()//1000
                if raw.strip():
                    if raw.startswith(b'SYNC_REQ,'):
                        try:
                            _,halter,t1_text=raw.decode('ascii').strip().split(',')
                            t1=int(t1_text)
                            if halter not in ('H1','H2') or not 0<=t1<2**63:
                                raise ValueError('Identificador ou timestamp inválido.')
                            t2=received_us
                            t3=time.monotonic_ns()//1000
                            self.request.sendall(f'SYNC_REPLY,{t1},{t2},{t3}\n'.encode('ascii'))
                            pending[(halter,t1)]=(t2,t3)
                        except (ValueError,UnicodeError,OSError) as exc:
                            rec.process(raw,cid,f'SYNC_REQ inválido: {exc}')
                    elif raw.startswith(b'SYNC_RESULT,'):
                        try:
                            _,halter,*stamps=raw.decode('ascii').strip().split(',')
                            if len(stamps)!=4 or halter not in ('H1','H2'):
                                raise ValueError('Formato inválido.')
                            t1,t2,t3,t4=map(int,stamps)
                            if pending.pop((halter,t1),None)!=(t2,t3) or not t1<=t4 or not t2<=t3:
                                raise ValueError('Resposta sem pedido correspondente.')
                            delay=(t4-t1)-(t3-t2)
                            if not 0<=delay<1_000_000:
                                raise ValueError('Tempo de ida e volta inválido.')
                            rec.record_sync(dict(halter_id=halter,connection_id=cid,
                                t1_esp_us=t1,t2_server_us=t2,t3_server_us=t3,t4_esp_us=t4,
                                server_minus_esp_us=((t2-t1)+(t3-t4))/2,
                                round_trip_us=delay,received_monotonic_ns=time.monotonic_ns(),
                                received_utc=utc_now()))
                        except (ValueError,UnicodeError) as exc:
                            rec.process(raw,cid,f'SYNC_RESULT inválido: {exc}')
                    else:
                        rec.process(raw,cid)
            if len(buf)>65536:
                rec.process(buf,cid,'Linha longa demais.');buf=b'';break
        if buf and not rec.shutdown.is_set():
            rec.process(buf,cid,'Mensagem incompleta na desconexão.')


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True


def analyze_quality(path, duration, invalid=0, storage_error=None):
    """Lacunas medidas por sensor, inclusive entre conexões e nas bordas.
    Tempo de recepção não separa atraso de transporte de perda de aquisição.
    """
    sensors=defaultdict(list); pairs={}; counts={h:Counter() for h in ('H1','H2')}
    with Path(path).open(encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            h,s=row['halter_id'],row['sensor']
            item=dict(seq=int(row['seq']),t_ms=int(row['t_ms']),connection_id=int(row['connection_id']),receive_s=float(row['elapsed_receive_s']))
            sensors[(h,s)].append(item);counts[h]['valid_lines']+=1
            pair_key=(item['connection_id'],item['seq'])
            old=pairs.get(h)
            if old is None or old['key']!=pair_key:
                if old:
                    counts[h]['complete_pairs' if old['sensors']=={'A','B'} else 'incomplete_pairs']+=1
                old=dict(key=pair_key,sensors=set(),t=item['t_ms']);pairs[h]=old
            if s in old['sensors']:
                counts[h]['duplicate_sensors']+=1
            if item['t_ms']!=old['t']:
                counts[h]['timestamp_mismatches_within_pair']+=1
            old['sensors'].add(s)
    for h,p in pairs.items():
        counts[h]['complete_pairs' if p['sensors']=={'A','B'} else 'incomplete_pairs']+=1
    reports={};gap_events=[];clock_events=[]
    for h,s in sorted(EXPECTED):
        rows=sensors[(h,s)];gaps=[];clocks=[];missing=0;previous=None
        for row in rows:
            if previous:
                ds=row['seq']-previous['seq'];dt=row['t_ms']-previous['t_ms']
                same=row['connection_id']==previous['connection_id']
                if same and ds>1:
                    missing+=ds-1
                if ds<0 or dt<0 or not same:
                    near_wrap=previous['seq']>0xFFFF0000 or previous['t_ms']>0xFFFF0000
                    kind='probable_restart' if ds<0 and dt<0 and not near_wrap else 'connection_or_clock_change'
                    clocks.append(dict(sensor=f'{h}/{s}',kind=kind,previous=previous,current=row))
                if row['receive_s']-previous['receive_s']>GAP_THRESHOLD_S:
                    gaps.append(dict(sensor=f'{h}/{s}',kind='between_samples',start_receive_s=previous['receive_s'],end_receive_s=row['receive_s'],duration_s=row['receive_s']-previous['receive_s']))
            previous=row
        if not rows:
            gaps.append(dict(sensor=f'{h}/{s}',kind='entire_recording',start_receive_s=0,end_receive_s=duration,duration_s=duration))
        else:
            for kind,a,b in [('start',0,rows[0]['receive_s']),('end',rows[-1]['receive_s'],duration)]:
                if b-a>GAP_THRESHOLD_S:
                    gaps.append(dict(sensor=f'{h}/{s}',kind=kind,start_receive_s=a,end_receive_s=b,duration_s=b-a))
        reports[f'{h}/{s}']=dict(samples=len(rows),first_receive_s=rows[0]['receive_s'] if rows else None,last_receive_s=rows[-1]['receive_s'] if rows else None,
            missing_sequences_within_connections=missing,connections_with_data=len({x['connection_id'] for x in rows}),
            probable_restarts=sum(x['kind']=='probable_restart' for x in clocks),gaps_over_threshold=len(gaps))
        gap_events+=gaps;clock_events+=clocks
    halters={}
    for h in ('H1','H2'):
        keys=['valid_lines','complete_pairs','incomplete_pairs','duplicate_sensors','timestamp_mismatches_within_pair']
        halters[h]={k:counts[h][k] for k in keys}
        halters[h]['connections_with_data']=len({x['connection_id'] for s in ('A','B') for x in sensors[(h,s)]})
        halters[h]['sequence_regressions']=sum(b['seq']<a['seq'] for a,b in zip(sensors[(h,'A')],sensors[(h,'A')][1:]))
    sync_path=Path(path).with_name('sync.jsonl')
    sync_events=[]
    if sync_path.exists():
        with sync_path.open(encoding='utf-8') as f:
            sync_events=[json.loads(line) for line in f if line.strip()]
    sync_summary={}
    for h in ('H1','H2'):
        events=[e for e in sync_events if e['halter_id']==h]
        best=min(events,key=lambda e:e['round_trip_us']) if events else None
        sync_summary[h]=dict(exchanges=len(events),best_round_trip_us=best['round_trip_us'] if best else None,
                             best_server_minus_esp_us=best['server_minus_esp_us'] if best else None)
    return dict(schema_version=3,collector_version=VERSION,halters=halters,sensors=reports,
        gap_threshold_s=GAP_THRESHOLD_S,gap_events=gap_events,clock_events=clock_events,
        invalid_lines=invalid,storage_error=storage_error,synchronization_estimates=sync_summary,
        bilateral_synchronization='offset_estimated_residual_not_validated' if all(sync_summary[h]['exchanges'] for h in ('H1','H2')) else 'insufficient_exchanges',
        requires_review=bool(gap_events or clock_events or invalid or storage_error or
            any(not sync_summary[h]['exchanges'] for h in ('H1','H2')) or
            any(v['missing_sequences_within_connections'] for v in reports.values()) or
            any(counts[h][k] for h in counts for k in ('incomplete_pairs','duplicate_sensors','timestamp_mismatches_within_pair'))),
        notes=['Gaps medem intervalos sem amostras recebidas; não provam a causa elétrica ou de transporte.',
               'Eventos A/B do mesmo halter podem descrever a mesma interrupção: não somar como falhas independentes.',
               'Sequências ausentes são calculadas apenas dentro de conexões; lacunas entre conexões estão em gap_events.',
               'Reinício provável exige regressão simultânea de sequência e relógio, fora da região de wraparound.',
               'Offsets de ida e volta assumem atrasos aproximadamente simétricos; não demonstram erro residual.',
               'Valide o alinhamento bilateral por um evento físico comum no início e no fim da sessão.',
               'Ausência de alertas não comprova sincronização, calibração ou qualidade biomecânica.'])


def plot_session(folder):
    import matplotlib
    import matplotlib.pyplot as plt
    groups=defaultdict(list)
    with (folder/'imu.csv').open(newline='',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            groups[(r['halter_id'],r['sensor'])].append(r)
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
    for (h,s),rows in sorted(groups.items()):
        xx=[];aa=[];gg=[];prev=None
        for r in rows:
            t=float(r['elapsed_receive_s'])
            if prev and (t-float(prev['elapsed_receive_s'])>GAP_THRESHOLD_S or r['connection_id']!=prev['connection_id'] or int(r['t_ms'])<int(prev['t_ms'])):
                xx.append(math.nan);aa.append(math.nan);gg.append(math.nan)
            xx.append(t);aa.append(math.sqrt(sum(int(r[k])**2 for k in ('ax','ay','az'))));gg.append(math.sqrt(sum(int(r[k])**2 for k in ('gx','gy','gz'))));prev=r
        for ax,values in zip(axes,(aa,gg)):
            ax.plot(xx,values,label=f'{h}/{s}',color='tab:blue' if h=='H1' else 'tab:orange',ls='-' if s=='A' else '--',lw=.8)
    for ax in axes:
        ax.grid(alpha=.2)
        if groups:
            ax.legend(ncol=4)
    axes[0].set_ylabel('|aceleração| bruta');axes[1].set_ylabel('|giroscópio| bruto')
    axes[1].set_xlabel('Tempo de recepção no PC (s)')
    fig.suptitle(f'{folder.name} — contagens brutas; sincronização bilateral não validada')
    fig.tight_layout();fig.savefig(folder/'preview.png',dpi=150)
    if matplotlib.get_backend().lower()!='agg':
        print('Feche o gráfico para preencher o relato.');plt.show()
    else:
        print('Gráfico salvo em preview.png (sem janela interativa).')
    plt.close(fig)


def main():
    if not sys.stdin.isatty():
        raise ValueError('Execute em um terminal interativo.')
    print(f'HalterCheck — coletor {VERSION}')
    condition=input('Condição pretendida [teste livre]: ').strip() or 'teste livre'
    left=choice('Dispositivo à esquerda h1/h2',('h1','h2'),'h2').upper()
    power=input('Alimentação [USB]: ').strip() or 'USB'
    video=choice('Vai filmar a coleta? s/n',('s','n'),'n')
    guided=choice('Guia sonoro subir/descer? s/n',('s','n'),'s')=='s'
    phase=integer('Segundos por fase',1,10,2) if guided else 2
    mode=choice('Encerramento manual/tempo',('manual','tempo'),'manual')
    duration=None
    if mode=='tempo':
        while True:
            duration=integer('Segundos de exercício (exclui preparação e finalização)',1,3600,20)
            if not guided or duration%(2*phase)==0:
                break
            print(f'Use múltiplo de {2*phase} s para terminar após uma descida solicitada.')
    port=integer('Porta TCP',1,65535,5000)
    base=ROOT/'data/raw';base.mkdir(parents=True,exist_ok=True)
    n=1
    while (base/f'P{n:03d}').exists():
        n+=1
    while True:
        session=input(f'Sessão [P{n:03d}]: ').strip() or f'P{n:03d}'
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',session):
            print('Use letras, números, hífen ou sublinhado.');continue
        folder=base/session
        try:
            folder.mkdir();break
        except FileExistsError:
            print('Sessão já existe. Escolha outra.')
    voice=None
    if guided:
        try:
            voice=Voice(folder);voice.play('subir');input('Teste de voz. Pressione Enter após ouvir.');voice.silence()
            if choice('Ouviu claramente? s/n',('s','n'),'s')=='n':
                print('Preparação cancelada; confira o áudio.');return
        except (OSError,RuntimeError,subprocess.SubprocessError) as exc:
            print(f'Voz indisponível: {exc}')
            if choice('Continuar sem guia? s/n',('s','n'),'n')=='n':
                return
            guided=False;voice=None
    timeline=Timeline(guided,duration,phase,5)
    metadata=dict(schema_version=2,collector_version=VERSION,session_id=session,created_utc=utc_now(),status='preparing',
        intended_condition=condition,left_device=left,right_device='H1' if left=='H2' else 'H2',power=power,
        mode=mode,requested_duration_s=duration,requested_duration_definition='exercise_only',
        preparation_s=timeline.exercise_start,finalization_s=5,video_planned=video=='s',raw_units='int16_counts',
        synchronization='offset_estimation_pending_physical_validation',tcp_port=port,reported_complete_repetitions=None,reported_incident=None,
        reported_notes=None,annotation_status='pending',confirmed_labels=None,
        voice_guidance=dict(enabled=guided,phase_duration_s=phase if guided else None,first_up_command_s=timeline.exercise_start if guided else None,
                            commands_file='cues.json',commands_are_confirmed_labels=False))
    save_json(folder/'metadata.json',metadata)
    if guided:
        print('0–5 s: repouso apoiado. Aos 5 s: prepare. Aos 10 s: subir/descer.')
    print('Enter solicita FINALIZAR: termine a fase em andamento e fique imóvel.')
    print('A gravação continua por mais 5 s. Ctrl+C encerra imediatamente.')
    print('O tempo extra não garante que a repetição terminou: isso será conferido nos sinais.')
    recorder=Recorder();server=None;worker=None;events=[];reason='cancelled_before_start'
    try:
        server=Server(('0.0.0.0',port),Handler);server.recorder=recorder
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        print('Aguardando os quatro sensores... Ctrl+C cancela.')
        while True:
            while not recorder.ready():
                time.sleep(.1)
            input('Sensores ativos. Enter para iniciar a contagem regressiva.')
            for i in (3,2,1):
                print(i,flush=True);time.sleep(1)
            if recorder.ready():
                break
            print('Sensor sem dados recentes. Aguardando novamente.')
        recorder.start(folder);metadata.update(status='recording',started_utc=recorder.started_utc)
        save_json(folder/'metadata.json',metadata)
        next_status=0
        while True:
            elapsed=(time.monotonic_ns()-recorder.start_ns)/1e9
            if recorder.failure:
                reason='storage_error';break
            request=enter_pressed()
            for word,scheduled in timeline.step(elapsed,request):
                dispatched=(time.monotonic_ns()-recorder.start_ns)/1e9
                event=dict(command=word,scheduled_elapsed_s=scheduled,dispatch_elapsed_s=dispatched,
                           dispatch_lateness_s=dispatched-scheduled,playback_requested=False,acoustic_onset_measured=False)
                events.append(event)
                print(f'>>> {word.upper()} <<<',flush=True)
                if word=='finalizar':
                    metadata['finish_requested_elapsed_s']=elapsed
                    print('Termine a fase e fique imóvel. Mais 5 segundos de gravação.')
                if voice and word in Voice.words:
                    try:
                        voice.play(word);event['playback_requested']=True
                    except (OSError,RuntimeError) as exc:
                        event['error']=str(exc);voice=None
                        print('Falha na voz; siga as mensagens na tela. Dados continuam sendo gravados.')
            if timeline.done:
                reason=timeline.reason;break
            if elapsed>=next_status:
                count,status=recorder.status();print(f'{elapsed:.1f}s | {count} linhas | {status}')
                next_status=elapsed+1
            time.sleep(.02)
    except KeyboardInterrupt:
        reason='keyboard_interrupt'
    except (OSError,EOFError) as exc:
        reason='error';metadata['error']=str(exc);print(f'Erro: {exc}')
    finally:
        recorder.stop();recorder.shutdown.set()
        if voice:
            try:
                voice.silence()
            except OSError:
                pass
        if server:
            server.shutdown();server.server_close()
        if worker:
            worker.join(timeout=2)
        metadata.update(finished_utc=utc_now(),stop_reason=reason,status='recorded' if recorder.start_ns is not None else 'cancelled')
        if recorder.start_ns is not None:
            metadata['actual_duration_s']=(recorder.stop_ns-recorder.start_ns)/1e9
        if recorder.failure:
            metadata.update(status='storage_error',storage_error=recorder.failure)
        save_json(folder/'metadata.json',metadata)
        save_json(folder/'cues.json',dict(timebase='pc_monotonic_since_recording_start',role='instructions_not_labels',events=events))
    if recorder.start_ns is None:
        print('Coleta não iniciada.');return
    print(f'Dados salvos: {folder}')
    quality=analyze_quality(folder/'imu.csv',metadata['actual_duration_s'],recorder.invalid,recorder.failure)
    save_json(folder/'quality.json',quality)
    print(json.dumps(quality['halters'],indent=2,ensure_ascii=False))
    print('Sincronização estimada:',json.dumps(quality['synchronization_estimates'],ensure_ascii=False))
    print('Erro residual bilateral requer validação com evento físico comum.')
    if quality['requires_review']:
        print('ATENÇÃO: coleta requer revisão. Veja gap_events e clock_events em quality.json.')
        for e in quality['gap_events']:
            print(f"{e['sensor']}: intervalo sem recepção {e['start_receive_s']:.3f}–{e['end_receive_s']:.3f}s ({e['duration_s']:.3f}s)")
        for e in quality['clock_events']:
            print(f"{e['sensor']}: {e['kind']} em {e['current']['receive_s']:.3f}s")
    try:
        plot_session(folder)
    except Exception as exc:
        print(f'Não foi possível exibir o gráfico: {exc}. Dados preservados.')
    try:
        while True:
            answer=input('Repetições completas realmente feitas (Enter = não sei): ').strip()
            if not answer:
                break
            try:
                count=int(answer)
                if count>=0:
                    metadata['reported_complete_repetitions']=count;break
            except ValueError:
                pass
            print('Informe um inteiro não negativo ou Enter.')
        save_json(folder/'metadata.json',metadata)
        metadata['reported_incident']=choice('Houve interrupção, impacto ou tentativa incompleta? s/n/incerto',('s','n','incerto'),'n')
        save_json(folder/'metadata.json',metadata)
        metadata['reported_notes']=input('Observações: ').strip()
        metadata['video_recorded']=choice('O vídeo foi gravado? s/n',('s','n'),'n')=='s'
        metadata.update(annotation_status='self_report_recorded',annotated_utc=utc_now())
        save_json(folder/'metadata.json',metadata)
    except (KeyboardInterrupt,EOFError):
        print('Relato interrompido; respostas já salvas preservadas.')
    print('Concluído. Rótulos continuam pendentes de conferência externa.')


if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError) as exc:
        print(f'Não foi possível concluir: {exc}')
