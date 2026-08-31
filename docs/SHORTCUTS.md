# Quick logging from your phone (Apple Shortcuts, Android, browser)

`hermes-life-os-api` (see the README's Local REST API section) exposes
every tool over plain HTTP on your local network - no app, no
subscription, no new account. This doc walks through building a
one-tap "Log Mood" Shortcut, plus the Android and browser equivalents.

**Prerequisite:** the API server has to actually be reachable from your
phone. If your phone and computer are on the same Wi-Fi, use your
computer's local IP (e.g. `192.168.1.42`) instead of `127.0.0.1` when
building the shortcut - and start the server with `--host 0.0.0.0` so
it accepts connections from other devices. Read `demo/local_api.py`'s
security notes first: this API has no HTTPS or rate limiting of its
own, so only do this on a network you trust (e.g. home Wi-Fi), and
never port-forward it to the public internet.

```bash
hermes-life-os-api --host 0.0.0.0
```

## Apple Shortcuts - "Log Mood" in one tap

1. Open the **Shortcuts** app -> **+** (new shortcut).
2. Add action **Ask for Input** -> type **Number** -> prompt "Mood (1-10)?".
3. Add action **Get Contents of URL**:
   - URL: `http://192.168.1.42:8765/api/tools/log_mood` (use your
     computer's actual local IP and port).
   - Method: **POST**.
   - Headers: add `X-API-Key` = your `LIFE_OS_API_KEY` value.
   - Request Body: **JSON**, add a field `score` set to the **Provided
     Input** (Number) from step 2.
4. Add action **Show Notification** -> text: the result of **Get
   Contents of URL** (Hermes' tool response, e.g. "Mood logged: 8/10").
5. Name the shortcut "Log Mood", tap the **(i)** icon -> **Add to Home
   Screen** for a true one-tap icon, or add it as a **Back Tap**
   gesture in Settings -> Accessibility -> Touch for the fastest
   possible logging.

The same four-step pattern (Ask for Input -> Get Contents of URL ->
show the response) works for any tool - swap the URL's tool name and
the JSON body's fields to match. A few ready-made ones:

| Shortcut | URL | Body |
|---|---|---|
| Log water | `/api/tools/log_hydration` | `{"glasses": <number>}` |
| Log expense | `/api/tools/log_expense` | `{"amount": <number>, "category": "<text>"}` |
| Quick note | `/api/tools/remember` | `{"type": "note", "content": "<text>"}` |
| What's my Life Score? | `/api/tools/get_life_score` | `{}` |

For a Siri-triggerable version, add **Add to Siri** in step 5 and
record a phrase like "log my mood" - no typing required at all.

## Android (Tasker or the HTTP Shortcuts app)

The free **HTTP Shortcuts** app (F-Droid/Play Store) does this without
any scripting:

1. Add a new shortcut -> Method **POST**, URL as above.
2. Under **Headers**, add `X-API-Key`.
3. Under **Request Body**, choose **JSON** and enter the same body
   shape as the table above (Tasker/variables can substitute a
   prompted value in for a literal number/text).
4. Enable **Show response as notification** so you see Hermes' reply.
5. Add the shortcut to your home screen or a widget.

Tasker users can build the same thing with an **HTTP Request** action
directly, using a **Prompt** action beforehand to collect input.

## Browser bookmarklet (desktop quick-log)

For logging from a browser without opening a terminal, a bookmarklet
works for a fire-and-forget log (no response shown, since bookmarklets
can't easily display one back):

```
javascript:fetch('http://127.0.0.1:8765/api/tools/log_mood',{method:'POST',headers:{'X-API-Key':'YOUR_KEY','Content-Type':'application/json'},body:JSON.stringify({score:prompt('Mood 1-10?')})})
```

Save this as a bookmark (paste the whole thing as the URL) and clicking
it prompts for a mood score and logs it - swap the tool name/body for
any other quick-log tool the same way as the Shortcuts table above.

## Widgets

Neither iOS nor Android widgets can make their own HTTP calls without a
companion app, so a true home-screen widget isn't possible purely via
Shortcuts/Tasker - but the **Shortcuts** widget (iOS) or a Tasker
**Scene**/widget (Android) can each hold one-tap buttons that run the
shortcuts above, which is the closest zero-code equivalent.
