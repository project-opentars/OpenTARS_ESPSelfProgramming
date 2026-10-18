# openTARS Self-Programming (resumo em português)

Você abre a página da placa no celular e pede algo ("faça o LED respirar"). Uma **ponte** de um arquivo só, no seu computador, entrega o pedido ao programa de IA que você já usa (**Claude Code, Codex, OpenCode, Pi, Grok Build**), que escreve o código MicroPython e roda na placa. Sem chave de API e sem configurar modelo: vale o que esses programas já têm.

## Começar
1. `tools/flash.sh /dev/ttyACM0` (grava o MicroPython e **apaga** a placa) e `pip install mpremote` + `tools/deploy.sh /dev/ttyACM0`.
2. No celular, entre na rede aberta **opentars-xxxx**, abra **http://192.168.71.1**, em **Ajustes > Wi-Fi** escolha a sua rede e conecte. Volte o celular para o seu Wi-Fi e abra o endereço novo.
3. A página mostra um comando: cole-o num terminal **no computador que tem o programa de IA instalado e logado** e deixe aberto. Depois é só `python3 bridge.py`.

**Estado:** testado em uma placa ESP32-S3 com Claude Code, Codex, OpenCode e Grok Build (ponta a ponta). O Pi não estava logado na máquina de teste. Ollama não é suportado (só responde texto). ESP-NOW só testado com placas simuladas. A ponte só foi testada no Linux.

**Sem senha:** qualquer um no mesmo Wi-Fi roda código na placa. Os programas de IA rodam com permissões liberadas para executar os comandos da placa (numa pasta temporária vazia). Detalhes no `README.md`.
