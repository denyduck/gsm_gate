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

### SIM PIN

Pokud SIM karta vyžaduje PIN, `ModemManagerClient.connect()` (v `modem_manager.py`) ho automaticky odemkne pomocí PIN kódu z **Nastavení GSM brány** (pole "PIN SIM") přes `mmcli -i <sim> --pin=<kód>`. Pokud PIN chybí v nastavení a SIM je zamčená, `connect()` skončí jasnou `ModemError` ("SIM vyžaduje odemčení, ale v nastavení brány není vyplněný PIN") místo matoucího "modem není registrovaný". Ruční ověření/odemčení mimo appku:

```bash
mmcli -m 0 -J   # modem.generic.unlock-required - "--"/"none" = odemčeno
mmcli -i 0 --pin=1234
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

Běží **na hostu** (ne v Dockeru, potřebuje `systemctl`/`reboot`), kontrola každé 2 minuty přes systemd timer. Modem index se zjišťuje dynamicky přes `mmcli -L` (ne natvrdo `0`), stejně jako v appce – po USB resetu/restartu ModemManageru se totiž může změnit (viz incident 2026-09-11 výše). Eskalace podle toho, jak dlouho je modem nepřetržitě nezdravý (stav jiný než `registered`/`connected`), každá akce jen jednou za epizodu:

1. **5 minut** → `systemctl restart ModemManager`.
2. **10 minut** → logický USB reset modemu (`unbind`/`bind` – řeší i zaseknutý firmware, který samotný restart ModemManageru nespraví).
3. **20 minut** → `sudo reboot`.

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

0. **Nejrychlejší první pohled**: stránka **Telemetrie** v appce – graf síly signálu a tabulka výpadků za poslední hodiny často rovnou ukážou, jestli šlo o výpadek signálu/modemu, bez nutnosti hrabat se v logu. Stránka **Sebediagnostika** k tomu přidá konkrétní doporučení (kategorie "Provoz").

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

3. **Modem visí v `disabled` a sám se nezaregistruje?** Od `connect()` v `modem_manager.py` se v tomhle stavu appka sama pokusí modem zapnout (`mmcli -m X -e`) – typicky stačí počkat na další cyklus workeru. Pokud i po pár cyklech zůstává `disabled`, zkontroluj ručně:
   ```bash
   mmcli -m 0 -e
   ```
   - Selže s běžnou chybou (SIM/síť) → pokračuj podle chybové hlášky.
   - Selže s `MobileEquipment.Unknown: Unknown error` **a** modem odmítá i základní `ATZ` (ověříš přes debug mód ModemManageru, viz níže) → jde o zaseknutý firmware modemu, ne o appku ani o ModemManager. Jediné funkční řešení je **logický USB reset** (bez nutnosti fyzicky odpojovat napájení) – z `mmcli -m 0 -J` zjisti `generic.device` (sysfs cesta, poslední segment je USB port, např. `1-1.2`):
     ```bash
     echo '1-1.2' > /sys/bus/usb/drivers/usb/unbind
     sleep 3
     echo '1-1.2' > /sys/bus/usb/drivers/usb/bind
     ```
     Modem se re-enumeruje, obvykle s **novým indexem** (viděno v praxi: `modem0` → `modem1`). Appka si nový index od opravy z 2026-09-11 hledá dynamicky při každém `connect()` (viz incident níže), takže žádný zásah do configu není potřeba – stačí počkat na další cyklus workeru, restart kontejneru není nutný.

   Pro detailní diagnostiku na AT úrovni (jaký konkrétní příkaz/chyba to způsobuje) je potřeba ModemManager na chvíli přepnout do debug módu – běžně (`mmcli --command`) appka ani nikdo jiný raw AT příkazy poslat nemůže:
   ```bash
   systemctl stop ModemManager
   /usr/sbin/ModemManager --debug &
   # v druhém terminálu mezitím: mmcli -m 0 -e
   # po diagnostice vrátit zpět:
   kill %1   # nebo PID vypsaný ModemManagerem
   systemctl start ModemManager
   ```

4. **Vidí kontejner ModemManager vůbec?** (typická chyba po změně Dockeru/rebuildu)
   ```bash
   docker compose --profile rpi exec gsm_worker mmcli -L
   ```
   Pokud tohle selže s chybou o D-Bus spojení, zkontroluj mount `/run/dbus` v `docker-compose.yml` a že `ModemManager` běží na hostu (`systemctl status ModemManager`).

5. **Selhala konkrétní odchozí akce?** Detail chyby je jen v DB, ne v logu kontejneru:
   ```bash
   docker compose --profile rpi run --rm gsm_worker python manage.py shell
   ```
   ```python
   from dashboard.models import OutgoingAction
   a = OutgoingAction.objects.filter(status='FAILED').latest('created_at')
   print(a.id, a.execution_detail)
   ```

6. **Ruční test odeslání mimo naši aplikaci** – izoluje, jestli je problém v Django kódu, nebo v modemu/síti samotné:
   ```bash
   mmcli -m 0 --messaging-create-sms="text='test',number='+420...'"
   mmcli -s <index> --send
   ```

7. **Nehromadí se SMS na modemu?** (worker po zpracování maže, ale při ručním testování mimo appku se to může nahromadit)
   ```bash
   mmcli -m 0 --messaging-list-sms -J
   ```

8. **Restartoval se modem sám kvůli watchdogu?**
   ```bash
   journalctl -u gsm-watchdog.service --since "-1 hour"
   ```

9. **Docker síť/kontejnery v divném stavu?** Po `docker compose down` bez `--profile rpi` může zůstat `gsm_worker` s referencí na neexistující síť:
   ```bash
   docker compose --profile rpi rm -f gsm_worker
   docker compose --profile rpi up -d gsm_worker
   ```

## Incident 2026-09-11: `disabled` + zaseknutý enable + zastaralý index modemu

Reálný produkční výpadek – appka přestala mít signál, worker donekonečna hlásil `Modem není registrovaný v síti (aktuální stav: disabled)`. Diagnostika (přes `journalctl -u ModemManager --debug`, viz krok 3 výše) odhalila **tři nezávislé příčiny navrstvené na sobě**:

1. **Appka nikdy nevolala enable.** `ModemManagerClient.connect()` jen kontroloval `state`, a když nebyl `registered`/`connected`, rovnou to vzdal – i kdyby stačilo poslat `mmcli -m X -e`. Po jakémkoliv restartu ModemManageru (watchdog, aktualizace, `systemctl restart`) se modem vždy vrací do `disabled` jako výchozí stav, takže appka byla trvale odkázaná na ruční zásah. **Opraveno natrvalo** (`connect()` teď při `disabled` sám zavolá enable).

2. **`mmcli -m X -e` selhávalo s `MobileEquipment.Unknown: Unknown error`.** Debug mód ModemManageru poprvé ukázal, že modem odmítal i nejzákladnější `ATZ` (`<-- ERROR`). `mmcli -m 0 -r` (reset) hlásil `Cannot reset the modem: operation not supported` – přes ModemManager to řešit nešlo, pomohl jen **logický USB reset** (`unbind`/`bind`, viz krok 3 výše).

3. **Appka si po prvním rozpoznání index modemu natrvalo zapamatovala** (`ModemManagerClient._resolve_modem_index()` cachoval `self._modem_index` na celou dobu běhu procesu) a po USB re-enumeraci (index se změnil z `0` na `1`) se dál ptala na starý, neexistující index (`mmcli -m 0: couldn't find modem`), i když modem `mmcli -L` normálně viděl. **Opraveno natrvalo** (`connect()` teď index před každým resolve zahodí).

**Aktualizace téhož dne – reprodukce na úplně jiném hardwaru:** stejný `Unknown error` na `-e` nastal znovu o pár hodin později, tentokrát na **jiné fyzické Teltonice** (jiné IMEI) nasazené na **jiné RPi desce** (test migrace RPi4 → RPi5, stejná SD karta/SIM přenesená mezi zařízeními). Tohle prakticky vylučuje vadný kus hardwaru nebo problém specifický pro původní RPi4 (napájení, přehřátí) – ukazuje to na něco systémového, společného oběma sestavám:

- buď neshoda mezi ModemManagerem 1.20.4 (`generic` plugin – viz krok 3 výše, plugin `quectel` je nainstalovaný, ale MM ho na tenhle Teltonika model nenamapoval) a firmwarem téhle Teltonika revize (`ALA440_A.57.8_EQ102`),
- nebo časová podmínka (race condition) – ModemManager možná zkouší mluvit s modemem dřív, než je po USB enumeraci firmware modemu fakt připravený přijímat AT příkazy, a USB reset to "opraví" jen tím, že dá modemu druhý pokus s jiným časováním.

Kořenová příčina zatím není potvrzená – log za log, oprava je zatím jen recept na rychlé zotavení (USB reset), ne skutečná prevence. **Další krok k prozkoumání:** zkusit vynutit plugin `quectel` místo `generic` přes udev pravidlo (pokud je tahle Teltonika interně Quectel modul), nebo ověřit, jestli jde o známý bug konkrétně ve verzi ModemManager 1.20.4.

**Ponaučení:** body 1 a 3 byly softwarové bugy a jsou vyřešené natrvalo. Bod 2 zůstává nevyřešená hardwarová/firmwarová/timing anomálie – `gsm_watchdog.sh` byl proto rozšířen o automatický USB reset jako mezikrok mezi restartem ModemManageru a rebootem celé RPi (viz sekce [Watchdog](#watchdog) výše), ať se tenhle konkrétní scénář vyřeší sám i bez ručního zásahu, dokud nemáme skutečnou opravu.

## Historické poznámky (starý SIM7000E/GPIO UART setup)

Pro referenci, kdyby se v budoucnu řešil jiný modem typu SIM7000/SIM800 s GPIO UART (ne USB) místo ModemManager přístupu:

- RPi4/5 defaultně mapuje `/dev/ttyAMA0` na Bluetooth; GPIO UART piny (TXD/RXD) jsou pak na `/dev/ttyS0` (slabší mini-UART), pokud není v `config.txt` nastaveno `dtoverlay=disable-bt` + `enable_uart=1`.
- Sériová konzole (`console=ttyAMA0` v `/proc/cmdline`, služba `serial-getty@ttyAMA0.service`) musí být vypnutá (`raspi-config` → Interface Options → Serial Port), jinak si port "přetahuje" s modemem.
- `sudo reboot` **nevypíná napájení** GPIO periferií (jen restartuje OS) – pro skutečný power-cycle HAT modulu je potřeba napájení fyzicky odpojit a znovu připojit.
- `vcgencmd get_throttled` ukáže bitovou masku podpětí/přehřátí RPi, aktuální i historické od posledního bootu.
- Dva procesy nesmí mít otevřený stejný sériový port zároveň (worker + ruční `manage.py shell` test) – vede to k `AT timeout`/`Input/output error`. U ModemManager přístupu tohle riziko strukturálně odpadá, protože jediný vlastník portu je ModemManager démon, ne naše Python procesy.
