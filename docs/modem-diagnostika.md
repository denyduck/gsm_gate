# Modem – hardware, software stack a diagnostika

Tato příručka je určená pro budoucí ladění problémů s GSM modemem: co za hardware běží, jak je softwarově napojený, jaké příkazy použít při diagnostice a na co si dát pozor. Poznatky vychází z reálného ladění na produkčním zařízení, ne jen z dokumentace výrobce.

## Aktuální hardware: Teltonika Calyx 4G (EBD021)

| | |
|---|---|
| Model | Teltonika Calyx 4G, kód **EBD021** |
| Typ | Cellular Raspberry Pi HAT+ |
| Modem | 4G Cat 4, fallback na 3G/2G |
| Fyzické zapojení | Nasazený na 40pin GPIO header **a** propojený USB-C kabelem s RPi |
| Datový kanál | Interní USB (ne GPIO UART!) – modem se hlásí jako `/dev/ttyUSB0`–`ttyUSB3` |
| Operátor SIM | T-Mobile CZ |
| Číslo brány | +420733495119 |
| Provozní teplota | -40 °C až +75 °C |
| Baterie/buffer | Nemá konektor na baterii |
| Vestavěný failsafe | GPIO reset modemu řízený z RPi (dokumentováno výrobcem, nepoužíváme přímo – viz Watchdog níže) |

Dokumentace výrobce: [QSG Calyx](https://wiki.teltonika-networks.com/view/QSG_Calyx) · [EBD021 AT Commands](https://wiki.teltonika-networks.com/view/EBD021_AT_Commands)

**Důležité:** i když je HAT fyzicky nasazený na GPIO, AT komunikace jde přes **interní USB rozhraní**, ne přes GPIO UART. GPIO header řeší mechanické usazení, napájení a control piny (reset), ne datový přenos.

### Registrace USB modemu u kernel driveru (nutná po každém bootu)

Aby se modem vůbec objevil jako `/dev/ttyUSB*`, musí se u generického kernel driveru `option` zaregistrovat jeho USB vendor/product ID:

```bash
sudo modprobe usbserial
sudo modprobe option
echo "1d12 0101" | sudo tee /sys/bus/usb-serial/drivers/option1/new_id
```

**Tohle je runtime stav kernelu, ne trvalé nastavení** – po každém restartu RPi se ztrácí. Proto existuje `scripts/calyx-usb-serial.service` (systemd, spouští se automaticky při bootu před `ModemManager.service`) – instalace viz [Nasazení a obnova po havárii](nasazeni-a-obnova.md). Bez téhle služby (nebo ručního spuštění výše po každém restartu) `ModemManager` modem po rebootu vůbec neuvidí, i kdyby bylo všechno ostatní v pořádku.

## Historie: proč se přešlo z Waveshare SIM7000E

Původní hardware byl **Waveshare SIM7000E HAT** (NB-IoT/eMTC/EDGE/GPRS, GPIO UART na `/dev/ttyAMA0`, ruční AT příkazy přes `pyserial`). Po měsících provozu modem přestal reagovat na AT příkazy (`AT timeout`), zatímco síťová LED (`NET`) dál ukazovala normální registraci v síti. Diagnostika vyloučila postupně:

- napájení RPi (`vcgencmd get_throttled` čisté),
- přehřátí,
- konflikt se sériovou konzolí (`console=ttyAMA0`, `serial-getty`),
- konfiguraci Bluetooth/UART mapování (`dtoverlay=disable-bt`),
- fyzické posazení HATu (re-seat),
- a nakonec i samotnou RPi desku (test na **jiné** fyzické RPi se stejným HATem selhal identicky).

Závěr: pravděpodobná hardwarová závada UART rozhraní modulu, nejspíš způsobená kumulativním stresem z počátečního podpětí (potvrzeno historicky přes `vcgencmd get_throttled`) a TX proudových špiček bez bateriového bufferu (SIM7000E HAT žádný konektor na baterii neměl). Kód pro tento hardware (`dashboard/services/sim7000.py`) byl z repozitáře odstraněn, protože je nahrazený a nepoužívaný.

## Software stack

Vrstvy od hardwaru po naši aplikaci:

1. **ModemManager** – systémová služba (`systemd`) běžící přímo na hostu RPi (ne v Dockeru). Spravuje modem, drží si AT port pro sebe a nabízí ovládání přes D-Bus.
2. **mmcli** – příkazový klient pro ModemManager. Na hostu je nainstalovaný jako součást balíčku `modemmanager`.
3. **D-Bus** – komunikační kanál mezi `mmcli` a ModemManager démonem (systémová sběrnice, socket `/run/dbus/system_bus_socket`).
4. **`dashboard/services/modem_manager.py`** (`ModemManagerClient`) – Python wrapper v Django aplikaci; spouští `mmcli` přes `subprocess` s `--output-json` (`-J`) a parsuje výsledek.
5. **`dashboard/services/gsm_worker.py`** (`GsmWorkerService`) – business logika (fronta odchozích akcí, zpracování příchozích SMS, pravidla) – nezávislá na konkrétním HW, mluví jen s `ModemManagerClient` přes stejné rozhraní (`connect`, `send_sms`, `read_unread_sms`, `delete_sms`, `get_signal_quality`).

### Docker specifika

- Kontejner `gsm_worker` **nemapuje** žádné `/dev/tty*` zařízení – modem si drží ModemManager na hostu, ne kontejner.
- Místo toho se do kontejneru mountuje D-Bus socket z hostu (`docker-compose.yml`, služba `gsm_worker`):
  ```yaml
  volumes:
    - ./django_app:/usr/src/app
    - /run/dbus:/run/dbus
  ```
- `Dockerfile_django` instaluje balíček `modemmanager` – ale jen kvůli binárce `mmcli`. Uvnitř kontejneru neběží systemd, takže se tam žádný druhý ModemManager démon sám nespustí.

## Diagnostické příkazy (cheatsheet)

Všechny `mmcli` příkazy níže lze spustit buď přímo na hostu (RPi terminál), nebo z kontejneru přes `docker compose --profile rpi exec gsm_worker mmcli ...`.

### Základní stav

```bash
mmcli -L                # seznam modemů, co ModemManager vidí
mmcli -m 0               # detail modemu, čitelný formát
mmcli -m 0 -J             # detail modemu jako JSON
```

Klíčové položky ve výstupu:

- `state` – měl by být `registered` nebo `connected`
- `access tech` – `lte` / `umts` / `gsm`
- `signal quality` – **procenta (0–100 %)**, ne CSQ škála
- `operator name` – `T-Mobile CZ`
- `own` (sekce Numbers) – číslo brány

### SMS

```bash
mmcli -m 0 --messaging-list-sms -J
mmcli -s <index> -J
mmcli -m 0 --messaging-create-sms="text='...',number='+420...'"
mmcli -s <index> --send
mmcli -m 0 --messaging-delete-sms=/org/freedesktop/ModemManager1/SMS/<index>
```

### Služba ModemManager

```bash
systemctl status ModemManager
systemctl restart ModemManager
journalctl -u ModemManager -f
```

## Známé zvláštnosti mmcli JSON výstupu

Zjištěno empiricky během integrace (ne z oficiální dokumentace – Teltonika/ModemManager dokumentace tohle nezmiňuje). Berte jako ověřenou realitu na naší verzi ModemManageru, ne obecnou pravdu:

1. **`--messaging-create-sms` vrací cestu k nové SMS vnořeně**, ne tak, jak by člověk čekal podle analogie s jinými příkazy:
   ```json
   {"modem": {"messaging": {"created-sms": "/org/freedesktop/ModemManager1/SMS/16"}}}
   ```
   Ne `sms.dbus-path` (to je formát u `mmcli -s <idx> -J`, jiného příkazu pro čtení detailu existující SMS).

2. **Akční příkazy (`--send`, `--messaging-delete-sms`) často nevrací JSON vůbec**, i s `-J` flagem – vypíšou jen lidsky čitelné potvrzení, např. `'successfully deleted SMS from modem'`. Náš kód (`_run_mmcli()` v `modem_manager.py`) to řeší tak, že při návratovém kódu 0 (úspěch) a neparsovatelném výstupu vrátí prázdný slovník místo vyhození chyby – jinak by se úspěšné operace tvářily jako chybné.

3. **Síla signálu je v procentech (0–100 %)**, ne CSQ škála (0–31) jako u starého SIM7000E. `GatewaySettings.signal_dbm` proto u tohoto hardwaru vždy vrací `None` – chybí spolehlivý převodní vzorec z procent na dBm.

## Watchdog

Soubory: `scripts/gsm_watchdog.sh`, `scripts/gsm-watchdog.service`, `scripts/gsm-watchdog.timer`.

Běží **na hostu** (ne v Dockeru, potřebuje `systemctl`/`reboot`), kontrola každé 2 minuty přes systemd timer:

1. Sleduje `state` z `mmcli -m 0 -J`.
2. Není-li modem `registered`/`connected` déle než 5 minut → `systemctl restart ModemManager`.
3. Nepomůže-li to do 15 minut → `sudo reboot`.

Instalace/aktualizace watchdogu po změně skriptu v repu:

```bash
sudo cp scripts/gsm_watchdog.sh /usr/local/bin/gsm_watchdog.sh
sudo chmod +x /usr/local/bin/gsm_watchdog.sh
sudo cp scripts/gsm-watchdog.service scripts/gsm-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gsm-watchdog.timer
```

Kontrola stavu:

```bash
systemctl list-timers gsm-watchdog.timer
journalctl -u gsm-watchdog.service -n 50
```

V normálním provozu watchdog nic nepíše do logu – zprávy se objeví jen při detekci problému.

## Postup při diagnostice „SMS nechodí“ (checklist)

1. **Běží worker a dokončuje cykly bez chyb?**
   ```bash
   docker compose --profile rpi ps
   docker compose --profile rpi logs --tail=50 gsm_worker
   ```
   Hledej opakované `Cyklus dokončen: incoming=X, sent=X, failed=X`. Cokoliv jako `Modem chyba, čekám 10s...` znamená problém s modemem/mmcli.

2. **Je modem registrovaný v síti?**
   ```bash
   mmcli -m 0
   ```
   Čekáte `state: registered`, `signal quality` > 0 %, `operator name: T-Mobile CZ`.

3. **Vidí kontejner ModemManager vůbec?** (typická chyba po změně Dockeru/rebuildu)
   ```bash
   docker compose --profile rpi exec gsm_worker mmcli -L
   ```
   Pokud tohle selže s chybou o D-Bus spojení, zkontroluj mount `/run/dbus` v `docker-compose.yml` a že `ModemManager` běží na hostu (`systemctl status ModemManager`).

4. **Selhala konkrétní odchozí akce?** Detail chyby je jen v DB, ne v logu kontejneru:
   ```bash
   docker compose --profile rpi run --rm gsm_worker python manage.py shell
   ```
   ```python
   from dashboard.models import OutgoingAction
   a = OutgoingAction.objects.filter(status='FAILED').latest('created_at')
   print(a.id, a.execution_detail)
   ```

5. **Ruční test odeslání mimo naši aplikaci** – izoluje, jestli je problém v Django kódu, nebo v modemu/síti samotné:
   ```bash
   mmcli -m 0 --messaging-create-sms="text='test',number='+420...'"
   mmcli -s <index> --send
   ```

6. **Nehromadí se SMS na modemu?** (worker po zpracování maže, ale při ručním testování mimo appku se to může nahromadit)
   ```bash
   mmcli -m 0 --messaging-list-sms -J
   ```

7. **Restartoval se modem sám kvůli watchdogu?**
   ```bash
   journalctl -u gsm-watchdog.service --since "-1 hour"
   ```

8. **Docker síť/kontejnery v divném stavu?** Po `docker compose down` bez `--profile rpi` může zůstat `gsm_worker` s referencí na neexistující síť:
   ```bash
   docker compose --profile rpi rm -f gsm_worker
   docker compose --profile rpi up -d gsm_worker
   ```

## Historické poznámky (starý SIM7000E/GPIO UART setup)

Pro referenci, kdyby se v budoucnu řešil jiný modem typu SIM7000/SIM800 s GPIO UART (ne USB) místo ModemManager přístupu:

- RPi4/5 defaultně mapuje `/dev/ttyAMA0` na Bluetooth; GPIO UART piny (TXD/RXD) jsou pak na `/dev/ttyS0` (slabší mini-UART), pokud není v `config.txt` nastaveno `dtoverlay=disable-bt` + `enable_uart=1`.
- Sériová konzole (`console=ttyAMA0` v `/proc/cmdline`, služba `serial-getty@ttyAMA0.service`) musí být vypnutá (`raspi-config` → Interface Options → Serial Port), jinak si port "přetahuje" s modemem.
- `sudo reboot` **nevypíná napájení** GPIO periferií (jen restartuje OS) – pro skutečný power-cycle HAT modulu je potřeba napájení fyzicky odpojit a znovu připojit.
- `vcgencmd get_throttled` ukáže bitovou masku podpětí/přehřátí RPi, aktuální i historické od posledního bootu.
- Dva procesy nesmí mít otevřený stejný sériový port zároveň (worker + ruční `manage.py shell` test) – vede to k `AT timeout`/`Input/output error`. U ModemManager přístupu tohle riziko strukturálně odpadá, protože jediný vlastník portu je ModemManager démon, ne naše Python procesy.
