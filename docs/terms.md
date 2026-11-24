# Terms

Benzinga's data is licensed to each firm under its own agreement with
Benzinga. Using this plugin, your deployment calls Benzinga's API with your
firm's own key, and records what Benzinga returns into your deployment's own
lake. Nothing is shared between deployments.

What your firm may do with the data, including whether it may be displayed
to people or used only internally, is set by your agreement with Benzinga,
as Benzinga states it. The plugin enforces none of it: a deployment admin
sets the dataset's licence on the **Data sources** page to match the
agreement.

Benzinga's rows carry ISINs and CUSIPs, which are licensed separately. The
plugin uses them only while it reads a row, and neither keeps nor sends
them.

This plugin is not affiliated with or endorsed by Benzinga.
