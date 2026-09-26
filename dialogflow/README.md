# IVR reporting with Dialogflow CX

Health workers without smartphones call a toll-free number. A Dialogflow CX agent (telephony
integration, e.g. via a CCAI / Exotel / Knowlarity SIP gateway) asks the questions by voice in
the caller's language, fills slots, and calls the PHC Pulse webhook to save the report.

## Agent setup

1. **Languages:** default `hi`, plus `ta`, `kn`, `or`, `te`, `bn`, `mr`, `en` (one agent, many languages).
2. **Session parameters** (set on the Start page from the caller ID):
   `caller_phone` = `$session.params.telephony-caller-id`.
3. **Flow `daily-report`**, one page per question with `@sys.number` slots:

   | Parameter | Prompt (hi) |
   |---|---|
   | `pcm` | पैरासिटामोल की कितनी स्ट्रिप बची हैं? |
   | `ors` | ओआरएस के कितने पैकेट बचे हैं? |
   | `beds` | अभी कितने बिस्तर भरे हैं? |
   | `staff` | आज कितने स्टाफ उपस्थित हैं? |
   | `opd` | आज ओपीडी में कितने मरीज़ आए? |

   Any drug code in lower case (`pcm`, `ors`, `znc`, `amx`, `ifa`, `met`, `aml`, `act`, `asv`, `oxy`)
   is accepted as a parameter. An optional free-text `utterance` parameter is also parsed.
4. **Webhook:** `POST https://<cloud-run-url>/api/dialogflow/webhook`, tag `submit-report` on the
   final page's fulfillment. The response's `fulfillment_response` contains the read-back in the
   caller's language, which the agent speaks before hanging up.
5. **Plausibility check:** if a number looks wrong for that PHC (e.g. "fifteen" heard for "fifty",
   boxes counted as strips), the webhook does **not** save. It reads the numbers back with a
   "please check, say yes if correct" question and sets the session parameter
   `needs_confirmation = true`. Add a route on that condition: on a yes intent set
   `confirmed = true` and call `submit-report` again (the report is then saved with the warnings
   kept for audit); otherwise go back to the question pages to collect the corrected numbers.
6. **Languages:** the read-back and the check prompt exist for English and all 22 scheduled
   languages (`backend/app/phrases.py`); pick them with the agent's language code.

## Test without telephony

The **USSD · SMS · IVR** page of the dashboard sends exactly the webhook request that Dialogflow
would send, or run:

```bash
curl -X POST https://<url>/api/dialogflow/webhook -H 'Content-Type: application/json' -d '{
  "languageCode": "hi", "fulfillmentInfo": {"tag": "submit-report"},
  "sessionInfo": {"parameters": {"caller_phone": "+919000000022", "pcm": 90, "beds": 5, "staff": 8}}}'
```

Registered demo numbers are `+9190000000NN`, where `NN` is the PHC id (e.g. `+919000000022` → PHC-22).
