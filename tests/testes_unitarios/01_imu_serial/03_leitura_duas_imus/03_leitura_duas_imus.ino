#include <Wire.h>

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;

constexpr uint8_t IMU_A_ADDRESS = 0x68;
constexpr uint8_t IMU_B_ADDRESS = 0x69;

constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr uint32_t I2C_FREQUENCY = 100000;

constexpr uint32_t SAMPLE_FREQUENCY_HZ = 50;
constexpr uint32_t SAMPLE_INTERVAL_US =
    1000000UL / SAMPLE_FREQUENCY_HZ;

// Registradores compatíveis com MPU-6050 e MPU-6500.
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
  int16_t temperature;
  int16_t gx;
  int16_t gy;
  int16_t gz;
};

uint32_t sequenceNumber = 0;
uint32_t nextSampleUs = 0;

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

const char* identifyModel(uint8_t whoAmI) {
  if (whoAmI == 0x68) {
    return "MPU-6050";
  }

  if (whoAmI == 0x70) {
    return "MPU-6500";
  }

  return nullptr;
}

bool configureImu(uint8_t deviceAddress) {
  if (!writeRegister(deviceAddress, REG_PWR_MGMT_1, 0x00)) {
    return false;
  }

  delay(100);

  // Filtro digital nível 3.
  if (!writeRegister(deviceAddress, REG_CONFIG, 0x03)) {
    return false;
  }

  // Frequência interna aproximada de 50 Hz.
  if (!writeRegister(deviceAddress, REG_SMPLRT_DIV, 19)) {
    return false;
  }

  // Giroscópio em ±250 °/s.
  if (!writeRegister(deviceAddress, REG_GYRO_CONFIG, 0x00)) {
    return false;
  }

  // Acelerômetro em ±2 g.
  if (!writeRegister(deviceAddress, REG_ACCEL_CONFIG, 0x00)) {
    return false;
  }

  return true;
}

bool initializeImu(
    uint8_t deviceAddress,
    const char* sensorName
) {
  uint8_t whoAmI = 0;

  Serial.print("Inicializando IMU ");
  Serial.print(sensorName);
  Serial.print(" no endereco 0x");
  Serial.println(deviceAddress, HEX);

  if (!readRegister(
          deviceAddress,
          REG_WHO_AM_I,
          whoAmI
      )) {
    Serial.println("ERRO: falha de comunicacao.");
    return false;
  }

  Serial.print("WHO_AM_I: 0x");
  Serial.println(whoAmI, HEX);

  const char* model = identifyModel(whoAmI);

  if (model == nullptr) {
    Serial.println("ERRO: modelo de IMU nao reconhecido.");
    return false;
  }

  Serial.print("Modelo identificado: ");
  Serial.println(model);

  if (!configureImu(deviceAddress)) {
    Serial.println("ERRO: falha ao configurar a IMU.");
    return false;
  }

  Serial.println("IMU configurada.");
  Serial.println();

  return true;
}

bool readImu(uint8_t deviceAddress, ImuData& data) {
  uint8_t buffer[14];

  if (!readRegisters(
          deviceAddress,
          REG_ACCEL_XOUT_H,
          buffer,
          sizeof(buffer)
      )) {
    return false;
  }

  data.ax = combineBytes(buffer[0], buffer[1]);
  data.ay = combineBytes(buffer[2], buffer[3]);
  data.az = combineBytes(buffer[4], buffer[5]);

  data.temperature =
      combineBytes(buffer[6], buffer[7]);

  data.gx = combineBytes(buffer[8], buffer[9]);
  data.gy = combineBytes(buffer[10], buffer[11]);
  data.gz = combineBytes(buffer[12], buffer[13]);

  return true;
}

void printImuData(
    uint32_t sequence,
    uint32_t timestampMs,
    char sensorName,
    const ImuData& data
) {
  Serial.print(sequence);
  Serial.print(',');

  Serial.print(timestampMs);
  Serial.print(',');

  Serial.print(sensorName);
  Serial.print(',');

  Serial.print(data.ax);
  Serial.print(',');

  Serial.print(data.ay);
  Serial.print(',');

  Serial.print(data.az);
  Serial.print(',');

  Serial.print(data.gx);
  Serial.print(',');

  Serial.print(data.gy);
  Serial.print(',');

  Serial.println(data.gz);
}

void stopExecution() {
  Serial.println();
  Serial.println("Teste interrompido.");

  while (true) {
    delay(1000);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);

  Serial.println();
  Serial.println("HalterCheck - Leitura simultanea das IMUs");
  Serial.println("-----------------------------------------");
  Serial.println();

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(I2C_FREQUENCY);

  const bool imuAReady =
      initializeImu(IMU_A_ADDRESS, "A");

  const bool imuBReady =
      initializeImu(IMU_B_ADDRESS, "B");

  if (!imuAReady || !imuBReady) {
    Serial.println(
        "ERRO: nao foi possivel inicializar as duas IMUs."
    );
    stopExecution();
  }

  Serial.println("As duas IMUs foram inicializadas.");
  Serial.println("Frequencia alvo: 50 Hz por sensor.");
  Serial.println();
  Serial.println(
      "seq,t_ms,sensor,ax,ay,az,gx,gy,gz"
  );

  nextSampleUs = micros();
}

void loop() {
  const uint32_t currentUs = micros();

  if (
      static_cast<int32_t>(currentUs - nextSampleUs) < 0
  ) {
    return;
  }

  nextSampleUs += SAMPLE_INTERVAL_US;

  ImuData imuAData;
  ImuData imuBData;

  const bool imuARead =
      readImu(IMU_A_ADDRESS, imuAData);

  const bool imuBRead =
      readImu(IMU_B_ADDRESS, imuBData);

  if (!imuARead || !imuBRead) {
    Serial.print("ERRO na sequencia ");
    Serial.print(sequenceNumber);
    Serial.print(": ");

    if (!imuARead) {
      Serial.print("falha na IMU A ");
    }

    if (!imuBRead) {
      Serial.print("falha na IMU B");
    }

    Serial.println();
    stopExecution();
  }

  const uint32_t timestampMs = millis();

  printImuData(
      sequenceNumber,
      timestampMs,
      'A',
      imuAData
  );

  printImuData(
      sequenceNumber,
      timestampMs,
      'B',
      imuBData
  );

  sequenceNumber++;
}