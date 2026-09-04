import argparse
import socket
import socketserver
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set


EXPECTED_HALTERS = {"H1", "H2"}
EXPECTED_SENSORS = {"A", "B"}
STATUS_INTERVAL_SECONDS = 5.0
ACTIVE_TIMEOUT_SECONDS = 3.0

console_lock = threading.Lock()


@dataclass
class HalterState:
    current_seq: Optional[int] = None
    current_timestamp: Optional[int] = None
    current_sensors: Set[str] = field(default_factory=set)

    valid_lines: int = 0
    lines_since_status: int = 0
    complete_pairs: int = 0
    incomplete_pairs: int = 0
    lost_sequences: int = 0
    duplicate_sensors: int = 0
    timestamp_mismatches: int = 0
    sequence_resets: int = 0

    last_received_at: Optional[float] = None


class DataValidator:
    def __init__(self) -> None:
        self.states: Dict[str, HalterState] = {}
        self.invalid_lines = 0
        self.lock = threading.Lock()
        self.last_status_at = time.monotonic()

    def register_invalid(self, message: str) -> None:
        with self.lock:
            self.invalid_lines += 1

        with console_lock:
            print(f"Linha inválida: {message}")

    def process_line(self, line: str) -> None:
        parts = line.split(",")

        if len(parts) != 10:
            self.register_invalid(
                f"quantidade de campos diferente de 10: {line}"
            )
            return

        halter_id = parts[0]
        sensor = parts[3]

        if halter_id not in EXPECTED_HALTERS:
            self.register_invalid(
                f"identificador de halter desconhecido: {line}"
            )
            return

        if sensor not in EXPECTED_SENSORS:
            self.register_invalid(
                f"identificador de sensor desconhecido: {line}"
            )
            return

        try:
            sequence = int(parts[1])
            timestamp_ms = int(parts[2])

            ax = int(parts[4])
            ay = int(parts[5])
            az = int(parts[6])
            gx = int(parts[7])
            gy = int(parts[8])
            gz = int(parts[9])
        except ValueError:
            self.register_invalid(
                f"campo numérico inválido: {line}"
            )
            return

        should_print_line = False

        with self.lock:
            state = self.states.setdefault(
                halter_id,
                HalterState(),
            )

            state.valid_lines += 1
            state.lines_since_status += 1
            state.last_received_at = time.monotonic()

            if state.valid_lines <= 6:
                should_print_line = True

            if state.current_seq is None:
                state.current_seq = sequence
                state.current_timestamp = timestamp_ms

            elif sequence != state.current_seq:
                self._finalize_current_pair(state)

                if sequence > state.current_seq + 1:
                    state.lost_sequences += (
                        sequence - state.current_seq - 1
                    )
                elif sequence < state.current_seq:
                    state.sequence_resets += 1

                state.current_seq = sequence
                state.current_timestamp = timestamp_ms
                state.current_sensors.clear()

            elif timestamp_ms != state.current_timestamp:
                state.timestamp_mismatches += 1

            if sensor in state.current_sensors:
                state.duplicate_sensors += 1

            state.current_sensors.add(sensor)

        if should_print_line:
            with console_lock:
                print(
                    f"{halter_id} seq={sequence} "
                    f"t={timestamp_ms} sensor={sensor} "
                    f"acc=({ax},{ay},{az}) "
                    f"gyro=({gx},{gy},{gz})"
                )

    @staticmethod
    def _finalize_current_pair(
        state: HalterState,
    ) -> None:
        if state.current_sensors == EXPECTED_SENSORS:
            state.complete_pairs += 1
        else:
            state.incomplete_pairs += 1

    def print_status(self) -> None:
        now = time.monotonic()

        with self.lock:
            elapsed = now - self.last_status_at
            self.last_status_at = now

            status_lines = []

            for halter_id in sorted(EXPECTED_HALTERS):
                state = self.states.get(halter_id)

                if state is None:
                    status_lines.append(
                        f"{halter_id}: ainda não detectado"
                    )
                    continue

                rate = (
                    state.lines_since_status / elapsed
                    if elapsed > 0
                    else 0.0
                )

                state.lines_since_status = 0

                age = (
                    now - state.last_received_at
                    if state.last_received_at is not None
                    else float("inf")
                )

                connection_status = (
                    "ativo"
                    if age <= ACTIVE_TIMEOUT_SECONDS
                    else "inativo"
                )

                status_lines.append(
                    f"{halter_id}: {connection_status}"
                    f" | {rate:.1f} linhas/s"
                    f" | total: {state.valid_lines}"
                    f" | último seq: {state.current_seq}"
                )

        with console_lock:
            print()
            print("Estado das transmissões")
            print("-----------------------")

            for line in status_lines:
                print(line)

    def print_summary(self) -> None:
        with self.lock:
            for state in self.states.values():
                if state.current_seq is not None:
                    self._finalize_current_pair(state)

            summary = {
                halter_id: state
                for halter_id, state in self.states.items()
            }

            invalid_lines = self.invalid_lines

        with console_lock:
            print()
            print("Resumo do teste simultâneo")
            print("--------------------------")

            for halter_id in sorted(EXPECTED_HALTERS):
                state = summary.get(halter_id)

                if state is None:
                    print(f"{halter_id}: nenhum dado recebido")
                    continue

                print(f"Halter {halter_id}")
                print(
                    f"  Linhas válidas: "
                    f"{state.valid_lines}"
                )
                print(
                    f"  Pares completos: "
                    f"{state.complete_pairs}"
                )
                print(
                    f"  Pares incompletos: "
                    f"{state.incomplete_pairs}"
                )
                print(
                    f"  Sequências ausentes: "
                    f"{state.lost_sequences}"
                )
                print(
                    f"  Sensores duplicados: "
                    f"{state.duplicate_sensors}"
                )
                print(
                    f"  Divergências de timestamp: "
                    f"{state.timestamp_mismatches}"
                )
                print(
                    f"  Reinícios de sequência: "
                    f"{state.sequence_resets}"
                )

            print(f"Linhas inválidas: {invalid_lines}")


validator = DataValidator()


class HalterRequestHandler(socketserver.BaseRequestHandler):
    def setup(self) -> None:
        self.request.settimeout(1.0)

        with console_lock:
            print(
                f"Cliente conectado: "
                f"{self.client_address[0]}:"
                f"{self.client_address[1]}"
            )

    def handle(self) -> None:
        buffer = b""

        while True:
            try:
                data = self.request.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                break

            buffer += data

            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)

                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if line:
                    validator.process_line(line)

        remaining = buffer.decode(
            "utf-8",
            errors="replace",
        ).strip()

        if remaining:
            validator.register_invalid(
                f"mensagem incompleta: {remaining}"
            )

    def finish(self) -> None:
        with console_lock:
            print(
                f"Cliente desconectado: "
                f"{self.client_address[0]}:"
                f"{self.client_address[1]}"
            )


class ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server(host: str, port: int) -> None:
    server = ThreadedTCPServer(
        (host, port),
        HalterRequestHandler,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )

    print("HalterCheck - Servidor para dois halteres")
    print("-----------------------------------------")
    print(f"Escutando em {host}:{port}")
    print("Aguardando H1 e H2...")
    print("Pressione Ctrl+C para encerrar.")

    server_thread.start()

    try:
        while True:
            time.sleep(STATUS_INTERVAL_SECONDS)
            validator.print_status()

    except KeyboardInterrupt:
        print("\nEncerrando servidor...")

    finally:
        server.shutdown()
        server.server_close()
        server_thread.join()
        validator.print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Servidor TCP simultâneo do HalterCheck."
        )
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5000,
    )

    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()