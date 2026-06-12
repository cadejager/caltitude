# Gmail Connector — Read & Label the Inbox

Practical notes for using the Gmail connector to: **read every inbox email that is
missing a given label, then apply that label to those emails.**

> ⚠️ Session note: a Gmail connector enabled mid-session does **not** appear in the
> running session. Start a **new session** (or reconnect) so its tools load. The
> exact tool names below are the standard Gmail-connector verbs; confirm them with a
> tool search for `gmail` once the connector is live — the *workflow* is the same
> regardless of the exact names.

## Key concepts (this is the part that actually matters)

Gmail has **no folders** — everything is a **label**. "Inbox" is itself the built-in
label `INBOX`. Applying or removing a label is the same operation whether the label
is a system one (`INBOX`, `UNREAD`, `STARRED`) or one you created.

- **Messages** vs **threads**: a thread groups a conversation; a message is one email.
  Labels can be read/set at either level. For "label the emails in my inbox," operate
  on **messages** unless you specifically want whole conversations.
- **Label IDs vs names**: the API applies labels by **ID**, not display name. User
  labels often have IDs like `Label_1234567890`; system labels use their uppercase
  name (`INBOX`, `UNREAD`). So you must **look up the label's ID first**.
- **Search query (`q`)**: the single most useful tool. It's the same syntax as the
  Gmail search box. The negative-label operator is the whole trick here:
  - `in:inbox` — restrict to the inbox
  - `-label:"Processed"` — exclude anything already carrying that label
  - Combined: `in:inbox -label:"Processed"`  ← "inbox emails missing the label"
  - Label names with spaces must be quoted: `-label:"Needs Review"`. Gmail also
    accepts hyphenated forms (`-label:needs-review`); quoting is the safe choice.

## The workflow

### 1. Find (or create) the label, and get its ID
List labels and match by name to get the `id`. If it doesn't exist, create it
(create returns the new `id`). Keep that `id` — you need it in step 3.

### 2. Read the inbox emails that lack the label
Call the **list messages** tool with:

```
q = in:inbox -label:"YOUR_LABEL"
```

This returns message IDs (and usually thread IDs). The list endpoint is paginated —
it returns a `nextPageToken` when there are more results. **Loop on the page token**
until it's absent, or you'll silently process only the first page (~100 messages).

To actually read content (subject, from, body), call the **get message** tool per
message ID. Use `format=metadata` (with `headers=Subject,From,Date`) when you only
need headers — it's much cheaper than pulling full bodies.

### 3. Add the label to each message
Call the **modify message** tool per message ID:

- `addLabelIds = ["<label_id_from_step_1>"]`
- (leave `removeLabelIds` empty)

Modify is **additive and idempotent** — adding a label that's already present is a
no-op, so re-running the job is safe. If a batch-modify tool is available, prefer it:
it takes a list of message IDs + the label change in one call (far fewer requests).

### 4. Verify
Re-run the step-2 query. A correct run leaves **zero** results (every inbox email now
has the label, so the `-label:` filter excludes them all).

## Gotchas

- **Get the label ID, don't pass the name** to modify — passing a name silently fails
  or errors depending on the connector.
- **Paginate.** Don't trust a single page; follow `nextPageToken` to the end.
- **Messages vs threads consistency.** If you listed messages, modify messages. Mixing
  levels leads to "I labeled it but the thread still shows unlabeled" confusion.
- **`-label:` needs the exact label name** as Gmail stores it (case-insensitive, but
  spelling/spacing matters). Verify against the list-labels output.
- **Scope of "inbox".** `in:inbox` excludes archived/sent/trashed mail by design. If
  you mean "all mail without the label," drop `in:inbox` and use just `-label:"..."`.
- **Rate limits / volume.** Large inboxes mean many `get`/`modify` calls. Batch where
  possible and expect to page through results.

## Quick reference

| Goal | Query / call |
|------|--------------|
| Inbox emails missing a label | list messages, `q = in:inbox -label:"X"` |
| Read one email's headers | get message, `format=metadata`, `headers=Subject,From,Date` |
| Add label to an email | modify message, `addLabelIds=["Label_id"]` |
| Remove a label | modify message, `removeLabelIds=["Label_id"]` |
| Confirm done | re-run `in:inbox -label:"X"` → expect 0 results |
