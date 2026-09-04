#include <WiFi.h>
#include <Wire.h>

constexpr char HALTER_ID[] = "H2";

constexpr char WIFI_SSID[] = "CLARO_6DFDD9";
constexpr char WIFI_PASSWORD[] = "asdfghjkL";

// Deve ser o IPv4 do computador, não o IP do ESP32.
IPAddress SERVER_IP(192, 168, 0, 8);

constexpr uint16_t SERVER_PORT = 5000;

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;

constexpr uint8_t IMU_A_ADDRESS = 0x68;
constexpr uint8_t IMU_B_ADDRESS = 0x69;

constexpr uint32_t SAMPLE_INTERVAL_US = 20000;
constexpr uint32_t WIFI_RETRY_MS = 5000;
constexpr uint32_t TCP_RETRY_MS = 2000;
constexpr uint32_t STATUS_INTERVAL_MS = 5000;

constexpr uint8_t REG_SMPLRT_DIV = 0x19;
constexpr uint8_t REG_CONFIG = 0x1A;
constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t REG_WHO_AM_I = 0x75;

struct ImuData {
  int16_t ax;
  int16_t ay;
  int16_t az;
  int16_t gx;
  int16_t gy;
  int16_t gz;
};

WiFiClient tcpClient;

uint32_t sequenceNumber = 0;
uint32_t nextSampleUs = 0;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastTcpAttemptMs = 0;
uint32_t lastStatusMs = 0;
uint32_t sentPairs = 0;
uint32_t transmissionFailures = 0;

bool writeRegister(
    uint8_t deviceAddress,
    uint8_t registerAddress,
    uint8_t value
) {
  Wire.beginTransmission(deviceAddress);
  Wire.write(registerAddress);
  Wire.write(value);

  return Wire.endTransmission() == 0;
}

bool readRegisters(
    uint8_t deviceAddress,
    uint8_t initialRegister,
    uint8_t* buffer,
    uint8_t length
) {
  Wire.beginTransmission(deviceAddress);
  Wire.write(initialRegister);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t received =
      Wire.requestFrom(deviceAddress, length);

  if (received != length) {
    return false;
  }

  for (uint8_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

bool readRegister(
    uint8_t deviceAddress,
    uint8_t registerAddress,
    uint8_t& value
) {
  return readRegisters(
      deviceAddress,
      registerAddress,
      &value,
      1
  );
}

int16_t combineBytes(uint8_t highByte, uint8_t lowByte) {
  return static_cast<int16_t>(
      (static_cast<uint16_t>(highByte) << 8) | lowByte
  );
}

bool isSupportedImu(uint8_t whoAmI) {
  return whoAmI == 0x68 || whoAmI == 0x70;
}

bool configureImu(uint8_t address, char sensorName) {
  uint8_t whoAmI = 0;

  if (!readRegister(address, REG_WHO_AM_I, whoAmI)) {
    Serial.print("Falha ao acessar IMU ");
    Serial.println(sensorName);
    return false;
  }

  Serial.print("IMU ");
  Serial.print(sensorName);
  Serial.print(" | endereco 0x");
  Serial.print(address, HEX);
  Serial.print(" | WHO_AM_I 0x");
  Serial.println(whoAmI, HEX);

  if (!isSupportedImu(whoAmI)) {
    Serial.println("Modelo de IMU nao reconhecido.");
    return false;
  }

  if (!writeRegister(address, REG_PWR_MGMT_1, 0x00)) {
    return false;
  }

  delay(100);

  return
      writeRegister(address, REG_CONFIG, 0x03) &&
      writeRegister(address, REG_SMPLRT_DIV, 19) &&
      writeRegister(address, REG_GYRO_CONFIG, 0x00) &&
      writeRegister(address, REG_ACCEL_CONFIG, 0x00);
}

bool readImu(uint8_t address, ImuData& data) {
  uint8_t buffer[14];

  if (!readRegisters(
          address,
          REG_ACCEL_XOUT_H,
          buffer,
          sizeof(buffer)
      )) {
    return false;
  }

  data.ax = combineBytes(buffer[0], buffer[1]);
  data.ay = combineBytes(buffer[2], buffer[3]);
  data.az = combineBytes(buffer[4], buffer[5]);

  data.gx = combineBytes(buffer[8], buffer[9]);
  data.gy = combineBytes(buffer[10], buffer[11]);
  data.gz = combineBytes(buffer[12], buffer[13]);

  return true;
}

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

bool sendPair(
    uint32_t sequence,
    uint32_t timestampMs,
    const ImuData& imuA,
    const ImuData& imuB
) {
  char message[256];

  const int length = snprintf(
      message,
      sizeof(message),
      "%s,%lu,%lu,A,%d,%d,%d,%d,%d,%d\n"
      "%s,%lu,%lu,B,%d,%d,%d,%d,%d,%d\n",
      HALTER_ID,
      static_cast<unsigned long>(sequence),
      static_cast<unsigned long>(timestampMs),
      imuA.ax,
      imuA.ay,
      imuA.az,
      imuA.gx,
      imuA.gy,
      imuA.gz,
      HALTER_ID,
      static_cast<unsigned long>(sequence),
      static_cast<unsigned long>(timestampMs),
      imuB.ax,
      imuB.ay,
      imuB.az,
      imuB.gx,
      imuB.gy,
      imuB.gz
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

void sampleAndTransmit() {
  ImuData imuA;
  ImuData imuB;

  const bool imuARead =
      readImu(IMU_A_ADDRESS, imuA);

  const bool imuBRead =
      readImu(IMU_B_ADDRESS, imuB);

  if (!imuARead || !imuBRead) {
    Serial.println("Falha na leitura das IMUs.");
    return;
  }

  const uint32_t timestampMs = millis();

  if (tcpClient.connected()) {
    if (
        sendPair(
            sequenceNumber,
            timestampMs,
            imuA,
            imuB
        )
    ) {
      sentPairs++;
    } else {
      transmissionFailures++;
      tcpClient.stop();
    }
  }

  sequenceNumber++;
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

  Serial.print(" | seq: ");
  Serial.print(sequenceNumber);

  Serial.print(" | pares enviados: ");
  Serial.print(sentPairs);

  Serial.print(" | falhas: ");
  Serial.println(transmissionFailures);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Envio das IMUs por Wi-Fi");
  Serial.println("--------------------------------------");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  if (
      !configureImu(IMU_A_ADDRESS, 'A') ||
      !configureImu(IMU_B_ADDRESS, 'B')
  ) {
    Serial.println("Falha ao inicializar as IMUs.");

    while (true) {
      delay(1000);
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  lastWifiAttemptMs = millis();
  nextSampleUs = micros();

  Serial.println("IMUs configuradas.");
}

void loop() {
  maintainWifi();
  maintainTcpConnection();

  const uint32_t currentUs = micros();

  if (
      static_cast<int32_t>(
          currentUs - nextSampleUs
      ) >= 0
  ) {
    nextSampleUs += SAMPLE_INTERVAL_US;
    sampleAndTransmit();

    if (
        static_cast<int32_t>(
            micros() - nextSampleUs
        ) >= 0
    ) {
      nextSampleUs =
          micros() + SAMPLE_INTERVAL_US;
    }
  }

  printStatus();
}