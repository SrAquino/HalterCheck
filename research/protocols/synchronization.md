# Sincronização bilateral — piloto

## Relógios e mensagens

O ESP32 conserva um relógio monotônico local (`esp_timer_get_time`, em microssegundos).
As linhas de IMU mantêm dez campos, com `t_ms` calculado a partir do meio da
janela sequencial de leitura das IMUs A e B. A resolução gravada é de 1 ms.
O relógio do servidor é `time.monotonic_ns()`, convertido para microssegundos.
Não usar o horário de chegada do pacote como horário da aquisição da IMU.

A cada 10 s, cada ESP envia `SYNC_REQ,halter,t1`. O servidor registra `t2`
quando processa a linha e `t3` antes de transmitir `SYNC_REPLY,t1,t2,t3`.
O ESP registra `t4` ao completar a leitura da resposta e devolve
`SYNC_RESULT,halter,t1,t2,t3,t4`. A aquisição não aguarda a resposta.

O servidor calcula, em microssegundos:

```
offset_servidor_menos_esp = ((t2 - t1) + (t3 - t4)) / 2
ida_e_volta = (t4 - t1) - (t3 - t2)
tempo_servidor_estimado = t_ms * 1000 + offset_servidor_menos_esp
```

Essas trocas são salvas em `sync.jsonl`, com `connection_id`, relógios brutos,
offset e ida e volta. Usar trocas do mesmo `connection_id` que os dados da
sessão; após reinício ou reconexão, repetir a sincronização. Na análise,
selecionar trocas com menor ida e volta próximas da repetição e verificar a
variação do offset ao longo da gravação. A estimativa assume atrasos de ida
e volta aproximadamente simétricos; ida e volta pequena não demonstra erro
residual pequeno.

## Passos no equipamento

1. Trocar a senha Wi-Fi exposta no histórico público do repositório.
2. Copiar `secrets.example.h` para `secrets.h` no diretório do sketch,
   inserir localmente a rede e a senha novas, e manter `secrets.h` fora do Git.
3. Gravar o sketch em H1 e H2, alterando `HALTER_ID` para cada dispositivo.
4. Iniciar `python scripts/acquire.py` e aguardar ao menos três trocas
   `SYNC_RESULT` por dispositivo antes de gravar o piloto.
5. Apoiar ambos os halteres lado a lado em uma superfície rígida e gerar
   um evento mecânico comum perceptível nos dois sinais no início e no fim
   da sessão. Filmar esse teste. Não inferir simultaneidade apenas de dois
   impactos feitos separadamente com as mãos.
6. Conferir em `quality.json` a presença de estimativas H1 e H2; comparar
   os tempos corrigidos dos eventos comuns e registrar a diferença residual.
   Repetir o piloto se houver reconexões, lacunas ou eventos ambíguos.

A condição H3 só pode entrar na avaliação principal se a diferença residual
observada atender ao limite previamente escrito na metodologia: inferior a
um período de amostragem (20 ms nominais neste sketch). A decisão deve usar
os eventos físicos e a qualidade dos dados, não apenas a estimativa de offset.

## Limites

O instante `t_ms` representa o meio da leitura sequencial A/B, e não a
conversão instantânea de cada MPU-6050. O teste de evento comum verifica
alinhamento observável no arranjo do piloto, não calibra ângulos anatômicos.
