# openTARS Self-Programming (resumo em português)

Um agente de IA que **mora dentro da placa** (ESP32-S3 com MicroPython) e se programa sozinho: você abre a página da placa no celular, pede algo, e ele escreve o código, roda, lê o erro, corrige e guarda o que funciona na própria biblioteca (`/skills`). Usa modelos na nuvem (Gemini, OpenAI, Groq, OpenRouter) ou locais (Ollama/LM Studio no seu PC), e as placas conversam entre si por ESP-NOW, sem PC.

**Estado:** versão inicial (0.1.0), testada em **uma** placa ESP32-S3 com o Gemini. O ESP-NOW só foi testado com placas simuladas (ainda não entre duas placas reais) e os modelos locais (Ollama) ainda não foram testados no hardware.

## Começar
1. Baixe o MicroPython `ESP32_GENERIC_S3` variante **SPIRAM_OCT** em micropython.org para `firmware/`.
2. `tools/flash.sh /dev/ttyACM0` (apaga a placa).
3. `pip install mpremote` e `tools/deploy.sh /dev/ttyACM0`.
4. No celular, entre na rede aberta **opentars-xxxx** e abra **http://192.168.71.1**.
5. Em **Ajustes**: escolha o Wi-Fi, o provedor do modelo e a chave; reinicie a placa.

Para o Ollama do PC: ele precisa escutar na rede (`OLLAMA_HOST=0.0.0.0`) e o endereço em Ajustes é `http://<IP do PC>:11434/v1`.

**Sem senha:** qualquer pessoa no mesmo Wi-Fi pode abrir a página e rodar código na placa. Segure o BOOT ao ligar para o modo seguro (não roda os programas automáticos).

Testes: `python3 tests/test_core.py` (no PC) e `mpremote connect /dev/ttyACM0 run tests/smoke_board.py` (na placa). Detalhes no `README.md`.
