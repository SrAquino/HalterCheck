import argparse
import socket
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class HalterState:
    boot_id: Optional[int] = None
    last_sequence: Optional[int] = None

    valid_lines: int = 0
    missing_sequences: int = 0
    boot_changes: int = 0
    duplicated_or_reversed: int = 0


states: Dict[str, HalterState] = {}

invalid_lines = 0
tcp_connections = 0


def process_line(line: str) -> None:
    global invalid_lines

    parts = line.split(",")

    if len(parts) != 4:
        invalid_lines += 1
        print(f"Linha inválida: {line}")
        return

    halter_id = parts[0]

    try:
        boot_id = int(parts[1], 16)
        sequence = int(parts[2])
        timestamp_ms = int(parts[3])
    except ValueError:
        invalid_lines += 1
        print(f"Valor inválido: {line}")
        return

    state = states.setdefault(
        halter_id,
        HalterState(),
    )

    if state.boot_id is None:
        state.boot_id = boot_id

    elif boot_id != state.boot_id:
        state.boot_changes += 1

        print()
        print(
            f"ATENÇÃO: {halter_id} reiniciou. "
            f"Boot anterior: {state.boot_id:08X} "
            f"| novo boot: {boot_id:08X}"
        )

        state.boot_id = boot_id
        state.last_sequence = None

    if state.last_sequence is not None:
        if sequence > state.last_sequence + 1:
            missing = (
                sequence - state.last_sequence - 1
            )

            state.missing_sequences += missing

            print(
                f"{halter_id}: salto de sequência "
                f"{state.last_sequence} → {sequence} "
                f"({missing} ausentes)"
            )

        elif sequence <= state.last_sequence:
            state.duplicated_or_reversed += 1

            print(
                f"{halter_id}: sequência duplicada "
                f"ou invertida: {sequence}"
            )

    state.last_sequence = sequence
    state.valid_lines += 1

    if state.valid_lines <= 10:
        print(
            f"{halter_id} "
            f"boot={boot_id:08X} "
            f"seq={sequence} "
            f"t={timestamp_ms} ms"
        )

    elif state.valid_lines % 500 == 0:
        print(
            f"{halter_id}: "
            f"{state.valid_lines} mensagens "
            f"| último seq: {sequence}"
        )


def print_summary() -> None:
    print()
    print("Resumo do teste com bateria")
    print("---------------------------")
    print(f"Conexões TCP: {tcp_connections}")
    print(f"Linhas inválidas: {invalid_lines}")

    if not states:
        print("Nenhum dado válido recebido.")
        return

    for halter_id, state in states.items():
        print()
        print(f"Halter {halter_id}")
        print(f"  Boot atual: {state.boot_id:08X}")
        print(f"  Mensagens válidas: {state.valid_lines}")
        print(
            f"  Sequências ausentes: "
            f"{state.missing_sequences}"
        )
        print(
            f"  Reinicializações detectadas: "
            f"{state.boot_changes}"
        )
        print(
            f"  Duplicadas ou invertidas: "
            f"{state.duplicated_or_reversed}"
        )


def run_server(host: str, port: int) -> None:
    global tcp_connections

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    server.bind((host, port))
    server.listen()

    print("HalterCheck - Servidor de contagem")
    print("----------------------------------")
    print(f"Escutando em {host}:{port}")
    print("Aguardando o ESP32...")
    print("Pressione Ctrl+C para encerrar.")
    print()

    try:
        while True:
            connection, address = server.accept()
            tcp_connections += 1

            print()
            print(
                f"Conexão TCP #{tcp_connections}: "
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

            print(
                f"Conexão encerrada: {address[0]}"
            )
            print("Aguardando reconexão...")

    except KeyboardInterrupt:
        print("\nServidor interrompido.")

    finally:
        server.close()
        print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Servidor do teste Wi-Fi com bateria."
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