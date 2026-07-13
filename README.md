# OpenRazerGTK

Reimaginação GTK4/Libadwaita, nativa do GNOME, para controle de periféricos Razer via [OpenRazer](https://openrazer.github.io/) — DPI, taxa de sondagem, iluminação, bateria/energia e presets locais. Segue as convenções GNOME HIG em vez de portar a UI da Razer Synapse/Polychromatic.

Toda a interface é **guiada por capabilities**: nada é mostrado incondicionalmente. As seções exibidas (DPI, bateria, zonas de LED, etc.) são derivadas em runtime do que o dispositivo conectado realmente reporta via `python-openrazer`.

## Requisitos

- `openrazer-daemon` rodando (`systemctl --user status openrazer-daemon` ou equivalente)
- `python-openrazer` instalado
- GTK 4 + Libadwaita ≥ 1.4 e PyGObject

## Rodando em desenvolvimento

Sem necessidade de instalar:

```sh
python -m razer_gtk
```

## Status

v1 em desenvolvimento. Features adiadas (tray icon, autostart, empacotamento meson) estão documentadas em [`docs/pendente.md`](docs/pendente.md).
