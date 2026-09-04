#include <WiFi.h>
#include <esp_system.h>

constexpr char HALTER_ID[] = "H1";

constexpr char WIFI_SSID[] = "CLARO_6DFDD9";
constexpr char WIFI_PASSWORD[] = "asdfghjkL";

// IP do computador que executará o servidor.
IPAddress SERVER_IP(192, 168, 0, 2);

constexpr uint16_t SERVER_PORT = 5000;

constexpr uint32_t SAMPLE_INTERVAL_MS = 20;
constexpr uint32_t WIFI_RETRY_MS = 5000;
constexpr uint32_t TCP_RETRY_MS = 2000;
constexpr uint32_t STATUS_INTERVAL_MS = 5000;

WiFiClient tcpClient;

uint32_t bootId = 0;
uint32_t lastSequence = UINT32_MAX;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastTcpAttemptMs = 0;
uint32_t lastStatusMs = 0;

uint32_t sentMessages = 0;
uint32_t transmissionFailures = 0;

void maintainWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  tcpClient.stop();

  if (
      millis() - lastWifiAttemptMs <
      WIFI_RETRY_MS
  ) {
    return;
  }

  Serial.println("Tentando conectar ao Wi-Fi...");

  WiFi.disconnect(false, false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  lastWifiAttemptMs = millis();
}

void maintainTcpConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (tcpClient.connected()) {
    return;
  }

  if (
      millis() - lastTcpAttemptMs <
      TCP_RETRY_MS
  ) {
    return;
  }

  tcpClient.stop();

  Serial.print("Conectando ao servidor ");
  Serial.print(SERVER_IP);
  Serial.print(':');
  Serial.println(SERVER_PORT);

  if (tcpClient.connect(SERVER_IP, SERVER_PORT)) {
    tcpClient.setNoDelay(true);

    Serial.println("Servidor TCP conectado.");
  } else {
    Serial.println("Falha ao conectar ao servidor.");
  }

  lastTcpAttemptMs = millis();
}

bool sendCounter(
    uint32_t sequence,
    uint32_t timestampMs
) {
  char message[96];

  const int length = snprintf(
      message,
      sizeof(message),
      "%s,%08lX,%lu,%lu\n",
      HALTER_ID,
      static_cast<unsigned long>(bootId),
      static_cast<unsigned long>(sequence),
      static_cast<unsigned long>(timestampMs)
  );

  if (length <= 0 || length >= sizeof(message)) {
    return false;
  }

  const size_t sent = tcpClient.write(
      reinterpret_cast<const uint8_t*>(message),
      length
  );

  return sent == static_cast<size_t>(length);
}

void transmitCurrentSequence() {
  const uint32_t timestampMs = millis();

  const uint32_t currentSequence =
      timestampMs / SAMPLE_INTERVAL_MS;

  if (currentSequence == lastSequence) {
    return;
  }

  lastSequence = currentSequence;

  if (!tcpClient.connected()) {
    return;
  }

  if (
      sendCounter(
          currentSequence,
          timestampMs
      )
  ) {
    sentMessages++;
  } else {
    transmissionFailures++;
    tcpClient.stop();
  }
}

void printStatus() {
  if (
      millis() - lastStatusMs <
      STATUS_INTERVAL_MS
  ) {
    return;
  }

  lastStatusMs = millis();

  Serial.print("Wi-Fi: ");
  Serial.print(
      WiFi.status() == WL_CONNECTED
          ? "conectado"
          : "desconectado"
  );

  Serial.print(" | TCP: ");
  Serial.print(
      tcpClient.connected()
          ? "conectado"
          : "desconectado"
  );

  Serial.print(" | boot: ");
  Serial.print(bootId, HEX);

  Serial.print(" | seq: ");
  Serial.print(lastSequence);

  Serial.print(" | enviados: ");
  Serial.print(sentMessages);

  Serial.print(" | falhas: ");
  Serial.println(transmissionFailures);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  bootId = esp_random();

  Serial.println();
  Serial.println(
      "HalterCheck - Teste Wi-Fi com bateria"
  );
  Serial.println(
      "-------------------------------------"
  );

  Serial.print("Halter: ");
  Serial.println(HALTER_ID);

  Serial.print("Boot ID: ");
  Serial.println(bootId, HEX);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  lastWifiAttemptMs = millis();
}

void loop() {
  maintainWifi();
  maintainTcpConnection();
  transmitCurrentSequence();
  printStatus();
}