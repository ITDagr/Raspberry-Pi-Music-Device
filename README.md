<img width="2160" height="1130" alt="v3_Case_Prototype_2026-Sep-02_01-20-18AM-000_CustomizedView29021399754" src="https://github.com/user-attachments/assets/fa7c127c-6085-4c54-b308-e0e225429f4f" />
# Raspberry-Pi-Music-Device


A Bluetooth music player based on the Raspberry Pi Zero 2 W.

This is my Raspberry Pi Music Device, which was focused on my goal, the ability to disconnect from society while still having access to music through Bluetooth headphones. It is a primitive prototype that lacks a battery, a proper case, and the overall feature set such as LEDs. This was simply a proof of concept and firmware test.

Demo video of the v3 case prototype: [v3 Case Prototype v11.avi](v3%20Case%20Prototype%20v11.avi)

BOM:
- [Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- [Adafruit 1.54" 240x240 TFT display, ST7789 with EYESPI connector (product 3787)](https://www.adafruit.com/product/3787)
- [Adafruit EYESPI Pi Beret (product 5783)](https://www.adafruit.com/product/5783) (connects the EYESPI display to the Pi)
- [Adafruit ANO Directional Navigation and Scroll Wheel Rotary Encoder (product 5001)](https://www.adafruit.com/product/5001)
- [Adafruit DRV2605L Haptic Motor Controller (product 2305)](https://www.adafruit.com/product/2305)
- Any LRA or coin-style haptic motor, such as the [Adafruit Vibrating Mini Motor Disc (product 1201)](https://www.adafruit.com/product/1201)
- 12 M2.5 screws, such as the [Adafruit M2.5 screw and standoff set (product 3299)](https://www.adafruit.com/product/3299)

Limits: It currently functions on what I would consider is slow firmware with a plug needed to function. The Raspberry Pi struggles with real timing and tends to lag behind inputs causing what feels like slow responses. In its current form factor a battery could not be squeezed in. The case is not optimal to keep it properly enclosed. Overall this is just version 1, and there is a lot more to come.

Other Software: This device ships with 2 sets of AI Designed software. One runs the music engine, and the other runs a simple local AI. This device is great for interesting handheld code on a very powerful mobile computer for anyone interested

The code for both is in [software/](software/), with the local AI in [software/pizero-llm-demo/](software/pizero-llm-demo/). You can try the music engine in your browser here: [Raspberry Pi Music Device demo](https://itdagr.github.io/Raspberry-Pi-Music-Device/)


What's Next: I have long planned a version 2 of this simple prototype I built. I plan to build it around a low-power microcontroller with a separate Bluetooth radio and a custom PCB with a Teenage Engineering style appearance and feature set that is more focused on music listeners instead of creators.
