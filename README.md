<img width="2160" height="1130" alt="v3_Case_Prototype_2026-Sep-02_01-20-18AM-000_CustomizedView29021399754" src="https://github.com/user-attachments/assets/fa7c127c-6085-4c54-b308-e0e225429f4f" />
# Raspberry-Pi-Music-Device


A Bluetooth music player based on the Raspberry Pi Zero 2 W.

This is my Raspberry Pi Music Device, which was focused on a simple goal, the ability to disconnect from society while still having access to music through Bluetooth headphones or a speaker. It is a primitive prototype that lacks a battery, a proper case, and the overall feature set such as haptics and LEDs. This was simply a proof of concept and firmware test and was my first experience into the world of AI software design.

Demo video of the v3 case prototype: [v3 Case Prototype v11.avi](v3%20Case%20Prototype%20v11.avi)

BOM:
- Raspberry Pi Zero 2 W
- [Adafruit 1.54" 240x240 TFT display, ST7789 with EYESPI connector (product 3787)](https://www.adafruit.com/product/3787)
- [Adafruit EYESPI Pi Beret](https://learn.adafruit.com/eyespi-pi-beret) (connects the EYESPI display to the Pi)
- [Adafruit ANO Directional Navigation and Scroll Wheel Rotary Encoder (product 5001)](https://www.adafruit.com/product/5001)
- [Adafruit DRV2605L Haptic Motor Controller (product 2305)](https://www.adafruit.com/product/2305)
- Any LRA or coin-style haptic motor
- 12 M2.5 screws

Limits: It currently functions on what I would consider is slow firmware with a plug needed to function. The Raspberry Pi struggles with real timing and tends to lag behind inputs causing what feels like slow responses. In its current form factor a battery could not be squeezed in. The case is not optimal to keep it properly enclosed. Overall this is just version 1, and there is a lot more to come.

Other Software: This device ships with 2 sets of AI Designed software. One runs the music engine, and the other runs a simple local AI. This device is great for interesting handheld code on a very powerful mobile computer for anyone interested


What's Next: I have long planned a version 2 of this simple prototype I built. I plan to build it around an ESP32 and a custom PCB with a Teenage Engineering style appearance and feature set that is more focused on music listeners instead of creators.
