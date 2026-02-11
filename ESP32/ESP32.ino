#include <Arduino.h>
#include "OLED_Display.h"

#define OUT_PIN           2      // D2 输出
#define BUZZER_PIN        4      // 有源蜂鸣器（低电平触发）
#define KEY_PIN           15     // 按键
#define MAX_PACKET_LEN    64     // 最大包长度（字节）
#define PACKET_TIMEOUT_MS 100    // 包接收超时（毫秒）
#define HEARTBEAT_TIMEOUT 5000   // 心跳超时时间（毫秒）

// 创建OLED对象，使用默认引脚21(SDA)、22(SCL)，地址0x3C
OLED_Display oled;

// 接收状态机状态定义
enum UartState {
  STATE_IDLE,      // 空闲：等待 '<'
  STATE_RECEIVING  // 接收中：等待 '>'
};

UartState uart_state = STATE_IDLE;
char packet_buffer[MAX_PACKET_LEN];  // 固定缓冲区，避免内存碎片
uint8_t packet_index = 0;            // 当前写入位置
unsigned long packet_start_time = 0; // 包开始接收时间

bool serial_alarm = false;
bool key_alarm = false;
bool heartbeat_alive = false;

unsigned long last_heartbeat_time = 0;

HardwareSerial MySerial(1);

void setup() {
  Serial.begin(115200);
  MySerial.begin(115200, SERIAL_8N1, 16, 17); // RX=16, TX=17

  pinMode(OUT_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(KEY_PIN, INPUT_PULLUP);

  digitalWrite(OUT_PIN, LOW);
  digitalWrite(BUZZER_PIN, HIGH);

  last_heartbeat_time = millis();
  heartbeat_alive = true; //避免开机就报警

  // 初始化OLED
  if (!oled.begin()) {
      Serial.println("OLED初始化失败！");
      while (1);
  }
  oled.println("System Ready!");
}

/**
 * @brief 简单的校验和计算（和值取模 256）
 * 格式：<DATA,CHECKSUM>
 */
uint8_t calculateChecksum(const char* data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) {
    sum += (uint8_t)data[i];
  }
  return sum;
}

/**
 * @brief 解析完整的包内容（完全使用 C 风格字符串，避免内存碎片）
 * @param packet 缓冲区指针（格式如 "<ALARM:1>" 或 "<ALARM:1,4A>"）
 * @param len 数据长度
 */
void parsePacket(char* packet, uint8_t len) {
  // 查找最后一个逗号，判断是否有校验和
  char* commaPtr = strrchr(packet, ',');
  char* dataStart = packet + 1; // 跳过起始符 '<'
  
  if (commaPtr != NULL) {
    // 存在校验和格式 <DATA,CS>
    *commaPtr = '\0'; // 将逗号替换为结束符，暂时切分字符串以计算数据部分的校验和
    
    char* checksumPart = commaPtr + 1;
    // 去掉末尾可能的 '>' 以解析校验和数值
    char* endBracket = strchr(checksumPart, '>');
    if (endBracket) *endBracket = '\0';

    uint8_t receivedSum = (uint8_t)strtol(checksumPart, NULL, 16);
    uint8_t calculatedSum = calculateChecksum(dataStart, strlen(dataStart));
    
    if (receivedSum != calculatedSum) {
      Serial.println("[UART_ERROR] Checksum mismatch!");
      oled.println("[UART_ERROR] Checksum mismatch!");
      return;
    }
    // 校验通过，dataStart 现在指向的是纯数据部分
  } else {
    // 不含校验和，去掉末尾的 '>'
    if (len > 0 && packet[len-1] == '>') {
      packet[len-1] = '\0';
    }
  }

  // 使用 strcmp 进行指令比对，完全避免 String 动态分配
  if (strcmp(dataStart, "ALARM:1") == 0) {
    serial_alarm = true;
    Serial.println("[UART] Alarm ON");
  }
  else if (strcmp(dataStart, "ALARM:0") == 0) {
    serial_alarm = false;
    Serial.println("[UART] Alarm OFF");
  }
  else if (strcmp(dataStart, "HB") == 0) {
    heartbeat_alive = true;
    last_heartbeat_time = millis();
    Serial.println("[UART] Heartbeat");
    oled.println("[UART] Heartbeat");
  }
  else {
    Serial.print("[UART] Unknown packet data: ");
    Serial.println(dataStart);
  }
}

/**
 * @brief 串口接收处理函数（包含超时和溢出保护）
 */
void handleSerialReceive() {
  // 1. 超时检测：如果处于接收状态且超过预设时间未完成，则重置
  if (uart_state == STATE_RECEIVING && (millis() - packet_start_time > PACKET_TIMEOUT_MS)) {
    Serial.println("[UART_ERROR] Receive timeout, dropping buffer");
    uart_state = STATE_IDLE;
    packet_index = 0;
  }

  // 2. 循环读取可用数据
  while (MySerial.available()) {
    char c = MySerial.read();

    if (c == '<') {
      // 发现起始符，开始接收
      uart_state = STATE_RECEIVING;
      packet_index = 0;
      packet_start_time = millis();
      packet_buffer[packet_index++] = c;
    }
    else if (uart_state == STATE_RECEIVING) {
      // 3. 溢出检查：防止 packet_index 越界（留一个位置给结束符或 null）
      if (packet_index >= MAX_PACKET_LEN - 1) {
        Serial.println("[UART_ERROR] Buffer overflow, packet too long");
        uart_state = STATE_IDLE;
        packet_index = 0;
        continue;
      }

      packet_buffer[packet_index++] = c;

      if (c == '>') {
        // 4. 发现结束符，进行解析
        packet_buffer[packet_index] = '\0'; // 结尾补零方便转 String 或打印
        parsePacket(packet_buffer, packet_index);
        uart_state = STATE_IDLE;
        packet_index = 0;
      }
    }
  }
}

void loop() {

  /* ---------- 串口接收处理 ---------- */
  handleSerialReceive();

  /* ---------- 心跳超时检测 ---------- */
  if (millis() - last_heartbeat_time > HEARTBEAT_TIMEOUT) {
    heartbeat_alive = false;
  }

  /* ---------- 按键触发 ---------- */
  if (digitalRead(KEY_PIN) == LOW) {
    key_alarm = true;
  } else {
    key_alarm = false;
  }

  /* ---------- 报警逻辑 ---------- */
  bool comm_fault = !heartbeat_alive;  // 通信故障
  bool alarm_active = serial_alarm || key_alarm || comm_fault;

  if (alarm_active) {
    digitalWrite(OUT_PIN, HIGH);      // D2 高电平
    digitalWrite(BUZZER_PIN, LOW);    // 蜂鸣器响
  } else {
    digitalWrite(OUT_PIN, LOW);
    digitalWrite(BUZZER_PIN, HIGH);   // 蜂鸣器停
  }

  delay(10);  // 轻微防抖
}
