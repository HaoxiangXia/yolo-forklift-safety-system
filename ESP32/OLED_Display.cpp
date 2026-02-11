#include "OLED_Display.h"
#include <Arduino.h>

// 构造函数：保存I2C引脚和地址，初始化屏幕对象
OLED_Display::OLED_Display(uint8_t sda, uint8_t scl, uint8_t addr)
    : oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET),
      _sda(sda), _scl(scl), _addr(addr),
      _cursorX(0), _cursorY(0), _textSize(1), _textColor(SSD1306_WHITE) {}

// 初始化：启动I2C，初始化屏幕
bool OLED_Display::begin() {
    Wire.begin(_sda, _scl);
    if (!oled.begin(SSD1306_SWITCHCAPVCC, _addr)) {
        return false;
    }
    clear();
    setCursor(0, 0);
    oled.setTextSize(_textSize);
    oled.setTextColor(_textColor);
    return true;
}

void OLED_Display::clear() {
    oled.clearDisplay();
}

void OLED_Display::setCursor(int16_t x, int16_t y) {
    _cursorX = x;
    _cursorY = y;
    oled.setCursor(x, y);
}

void OLED_Display::display() {
    oled.display();
}

// 内部换行打印（自动折行）
void OLED_Display::printWrapped(const String& text) {
    int16_t x1, y1;
    uint16_t w, h;
    oled.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
    
    // 每行最多21个字符（字体1）
    const int maxCharsPerLine = 21;
    int len = text.length();
    int start = 0;
    while (start < len) {
        int end = min(start + maxCharsPerLine, len);
        oled.println(text.substring(start, end));
        start = end;
    }
}

void OLED_Display::print(const String& text) {
    oled.print(text);
}

void OLED_Display::println(const String& text) {
    oled.println(text);
}

// 显示串口消息：固定头部 + 消息正文
void OLED_Display::showSerialMessage(const String& message) {
    clear();
    setCursor(0, 0);
    oled.println("Serial Monitor:");
    oled.println("----------------");
    printWrapped(message);
    display();
}