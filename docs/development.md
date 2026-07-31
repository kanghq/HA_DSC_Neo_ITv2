# Development

## Layout

```
HA_DSC_Neo_ITv2/
├── custom_components/dsc_neo_itv2/
│   ├── __init__.py            setup/unload + service registration
│   ├── coordinator.py         panel state + ITv2Server lifecycle
│   ├── config_flow.py         user -> wait -> confirm, options, reauth, reconfigure
│   ├── entity.py              shared entity base
│   ├── alarm_control_panel.py binary_sensor.py sensor.py switch.py button.py
│   ├── storage.py             cached panel config
│   ├── repairs.py             trouble + auth Repairs issues
│   ├── diagnostics.py         redacted diagnostics
│   ├── zone_definitions.py    zone-definition byte -> device class / category
│   ├── zone_attributes.py     section [002] / [307] bit decoders
│   ├── zone_labels.py         label keyword -> device class
│   ├── const.py  manifest.json  services.yaml  strings.json  icons.json
│   ├── translations/          strings.json mirrors
│   ├── brand/                 local brand images
│   └── dsc_itv2/              pure-Python protocol library (no HA imports)
│       ├── crc.py  tlink_framing.py  itv2_framing.py  packet.py
│       ├── encryption.py  serdes.py  commands.py  messages.py  enums.py
│       └── session.py  server.py
├── docs/
├── tests/
│   ├── protocol/              no Home Assistant needed
│   └── components/            needs pytest-homeassistant-custom-component
├── hacs.json  pytest.ini  ruff.toml  requirements-test.txt
└── .github/workflows/
```

**Rule: nothing under `dsc_itv2/` may import `homeassistant`.** That boundary is
what makes the protocol layer testable without an event loop or an HA install,
and what would let it be split out to PyPI later. The same rule applies to
`zone_definitions.py`, `zone_attributes.py` and `zone_labels.py`, which are pure
lookup tables. `tests/protocol/test_layering.py` enforces all of it.

The protocol CI job installs no Home Assistant at all and runs
`tests/protocol` plus `tests/test_metadata.py`, so neither of those may import
`homeassistant` either.

## Setup

```bash
git clone https://github.com/LawPaul/HA_DSC_Neo_ITv2
cd HA_DSC_Neo_ITv2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-test.txt
```

`pytest-homeassistant-custom-component` pulls in the whole of Home Assistant and
is large. If you only want to work on the protocol layer:

```bash
pip install pytest pytest-asyncio pycryptodome
pytest tests/protocol
```

## Running tests

```bash
pytest                    # everything
pytest tests/protocol     # protocol layer only, no HA required
pytest tests/components   # Home Assistant integration tests
pytest -m protocol        # by marker
pytest --cov=custom_components/dsc_neo_itv2 --cov-report=term-missing
```

`tests/components/` is skipped automatically when
`pytest-homeassistant-custom-component` is not installed, so a bare
`pytest` still works in a minimal environment.

## Linting

```bash
ruff check .
ruff format --check .
```

## Working on the protocol layer

`SessionCodec` is a synchronous, I/O-free state machine. You test it by feeding
byte strings:

```python
codec = SessionCodec(ConnectionSettings(type2_access_code_hex="00" * 16))
events = codec.feed(wire_bytes_from_panel)
```

Everything below it is pure functions over `bytes`, so round-trip tests are the
natural style:

```python
out = bytearray()
write_compact_int(out, 0x1234)
assert read_compact_int(bytes(out), 0) == (0x1234, len(out))
```

To build realistic panel frames, compose the layers in order:

```python
packet   = build_packet(sender_seq, receiver_seq, Command.Simple_Ack)
framed   = add_framing(packet)          # length + CRC
payload  = cipher.encrypt(framed)       # AES-128-ECB, zero-padded
wire     = pack(integration_id, payload)  # TLink stuffing + delimiters
```

## Working on the Home Assistant layer

Integration tests use `pytest-homeassistant-custom-component`. The shared
fixtures in `tests/components/conftest.py` provide:

| Fixture | Purpose |
|---|---|
| `enable_custom_integrations` | required by the harness (autouse) |
| `mock_config_entry` | a `MockConfigEntry` with plausible credentials |
| `mock_coordinator` | a coordinator double with zones/partitions/trouble populated |

Do not hit the network in tests. Bind probes and the ITv2 server are patched.

## Adding a message type

1. Add the command to `Command` in `commands.py` if it isn't there.
2. Add a frozen dataclass in `messages.py` with a class-level `COMMAND`.
3. Write `encode_x(msg) -> bytes` and `decode_x(body) -> X` using `serdes`
   helpers.
4. Register both in `ENCODERS` / `DECODERS`.
5. Add a round-trip test in `tests/protocol/test_messages.py`.

Unknown commands must keep decoding to `DefaultMessage` rather than raising. A
panel firmware we've never seen must not be able to kill the session.

## Adding an entity

1. Add the state to `ZoneState` / `PartitionState` / the coordinator.
2. Update the notification handler that populates it and make sure it fires the
   right `SIGNAL_*`.
3. Add the entity class in the relevant platform module; subclass
   `DscNeoEntity`, set a stable `_attr_unique_id` and list your signals in
   `_signals()`.
4. Add the `translation_key` to both `strings.json` and `translations/en.json`,
   plus an icon in `icons.json` if needed. Both are looked up by
   `translation_key`, so an entity without one gets neither the name nor the
   icon. Setting `_attr_name` also silently defeats the `strings.json` name.
   `tests/test_metadata.py` fails on any unreachable entry.
5. Add a test.

## Conventions

- `from __future__ import annotations` at the top of every module.
- Modern type hints (`str | None`, `dict[int, ZoneState]`).
- Stable unique ids: `{entry_id}_<scope>_<n>[_<kind>]`. Never change an existing
  pattern without a migration.
- `_attr_has_entity_name = True` and a `translation_key` on every entity.
- Never log key material, PINs or the Integration ID.
- Cite the panel manual section (`[851][422]`, `[009][N]`, ...) in comments when
  encoding panel behaviour.

## Releasing

1. Bump `version` in `custom_components/dsc_neo_itv2/manifest.json`.
2. Tag `vX.Y.Z` and push the tag.
3. **Publish a GitHub release** for that tag, with the release notes as the
   body. HACS serves published releases, not bare tags, and shows the release
   body as the changelog. A tag on its own is invisible to HACS.

## Contributing

Issues and pull requests: <https://github.com/LawPaul/HA_DSC_Neo_ITv2>

Please run `pytest` and `ruff check .` before opening a PR, and **never include
real Integration IDs, access keys, PINs or unredacted captures** in code,
tests, issues or commits.
