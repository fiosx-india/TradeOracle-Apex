# TradeOracle Apex — incoming

இந்த folder தான் புதிய AI / Research / Signal engine-களுக்கான FRONT DOOR.

புதிய Python engine கிடைத்தால் இதற்குள் நேரடியாக போட வேண்டும்:

    incoming/
        new_engine.py

அதற்கு core files-ல் manual import / edit தேவையில்லை.

Pipeline:

    new_engine.py
          ↓
      incoming/
          ↓
    Auto Discovery
          ↓
      Validation
          ↓
      Benchmark
          ↓
     Registration
          ↓
      Master Brain
          ↓
        ACTIVE

ஒரு plugin குறைந்தபட்சமாக:
- PLUGIN_CLASS
- name
- capabilities
- analyze(context) அல்லது predict(context)

கொண்டிருக்க வேண்டும்.

Benchmark pass என்பது contract/smoke-test pass என்பதை மட்டும் குறிக்கும்.
Trading accuracy நிரூபிக்க historical + walk-forward validation அவசியம்.
