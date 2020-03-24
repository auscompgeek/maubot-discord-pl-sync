# maubot-discord-pl-sync
A [maubot] plugin to map Discord roles to Matrix power levels.

This works alongside an instance of [matrix-appservice-discord] to give
Discord users a given power level in a Matrix room when given a Discord role.

This is a workaround for [matrix-appservice-discord issue #542][GH-542].

[maubot]: https://maubot.xyz
[matrix-appservice-discord]: https://github.com/Half-Shot/matrix-appservice-discord
[GH-542]: https://github.com/Half-Shot/matrix-appservice-discord/issues/542

## Configuration
`rooms` is a mapping of Matrix room IDs to a mapping of Discord role names
to Matrix power levels.

`server_name` restricts the Matrix "users" this plugin will grant
power levels for within the given rooms
(i.e. the Matrix user ID must match `@_discord_*:<server_name>`).

## License
[AGPL v3](LICENSE) or later.
