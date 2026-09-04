import argparse
import socket
from dataclasses import dataclass, field


@dataclass
class HalterState:
    current_seq: int | None = None
    current_timestamp: int | None = None
    current_sensors: set[str] = field(default_factory=set)

    valid_lines: int = 0
    complete_pairs: int = 0
    incomplete_pairs: int = 0
    lost_sequences: int = 0
    duplicate_sensors: int = 0
    timestamp_mismatches: int = 0
    sequence_resets: int = 0


states: dict[str, HalterState] = {}
invalid_lines = 0


def process_line(line: str) -> None:
    global invalid_lines

    parts = line.split(",")

    if len(parts) != 10:
        invalid_lines += 1
        print(f"Linha inválida ({len(parts)} campos): {line}")
        return

    try:
        halter_id = parts[0]
        sequence = int(parts[1])
        timestamp_ms = int(parts[2])
        sensor = parts[3]

        ax = int(parts[4])
        ay = int(parts[5])
        az = int(parts[6])
        gx = int(parts[7])
        gy = int(parts[8])
        gz = int(parts[9])
    except ValueError:
        invalid_lines += 1
        print(f"Linha com valor inválido: {line}")
        return

    if sensor not in {"A", "B"}:
        invalid_lines += 1
        print(f"Sensor inválido: {line}")
        return

    state = states.setdefault(halter_id, HalterState())
    state.valid_lines += 1

    if state.current_seq is None:
        state.current_seq = sequence
        state.current_timestamp = timestamp_ms

    elif sequence != state.current_seq:
        if state.current_sensors == {"A", "B"}:
            state.complete_pairs += 1
        else:
            state.incomplete_pairs += 1

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

    if state.valid_lines <= 10:
        print(
            f"{halter_id} seq={sequence} "
            f"t={timestamp_ms} sensor={sensor} "
            f"acc=({ax},{ay},{az}) "
            f"gyro=({gx},{gy},{gz})"
        )

    elif state.valid_lines % 500 == 0:
        print(
            f"{halter_id}: {state.valid_lines} linhas válidas "
            f"| último seq: {sequence}"
        )


def finalize_states() -> None:
    for state in states.values():
        if state.current_seq is None:
            continue

        if state.current_sensors == {"A", "B"}:
            state.complete_pairs += 1
        else:
            state.incomplete_pairs += 1


def print_summary() -> None:
    finalize_states()

    print()
    print("Resumo do teste")
    print("----------------")

    if not states:
        print("Nenhum dado válido foi recebido.")
    else:
        for halter_id, state in states.items():
            print(f"Halter {halter_id}")
            print(f"  Linhas válidas: {state.valid_lines}")
            print(f"  Pares completos: {state.complete_pairs}")
            print(f"  Pares incompletos: {state.incomplete_pairs}")
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


def run_server(host: str, port: int) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    server.bind((host, port))
    server.listen()

    print("HalterCheck - Servidor TCP de teste")
    print("-----------------------------------")
    print(f"Escutando em {host}:{port}")
    print("Aguardando conexão do ESP32...")
    print("Pressione Ctrl+C para encerrar.")
    print()

    try:
        while True:
            connection, address = server.accept()

            print(
                f"ESP32 conectado: "
                f"{address[0]}:{address[1]}"
            )

            buffer = b""

            with connection:
                while True:
                    data = connection.recv(4096)

                    if not data:
                        break

                    buffer += data

                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(
                            b"\n",
                            1,
                        )

                        line = raw_line.decode(
                            "utf-8",
                            errors="replace",
                        ).strip()

                        if line:
                            process_line(line)

            print(f"Conexão encerrada: {address[0]}")
            print("Aguardando nova conexão...")

    except KeyboardInterrupt:
        print("\nServidor interrompido pelo usuário.")

    finally:
        server.close()
        print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Servidor TCP de teste do HalterCheck."
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