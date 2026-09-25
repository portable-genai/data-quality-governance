"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this dataset is not queued for review.",
  off: "Review routing is off in this deployment; this dataset is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// The datasets the local profile's fixture warehouse seeds, all fictional. There is no list route,
// so these are offered as suggestions and the field stays free text: a managed deployment's
// warehouse names its own datasets, and the service is the one that says whether it knows an id.
const SEEDED_DATASETS: { id: string; note: string }[] = [
  { id: "transactions_daily", note: "stale partition, duplicate id, null amounts" },
  { id: "customer_master", note: "clean and fresh" },
  { id: "marketing_events", note: "schema drift and a sensitive-category column" },
];

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [datasetId, setDatasetId] = useState(SEEDED_DATASETS[0].id);
  const [result, setResult] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function show(request: Promise<Response>) {
    setBusy(true);
    setFailed(false);
    try {
      const response = await request;
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  // The request is the dataset id and nothing else: the verdict, the metrics and the actor all
  // come from the service, which is the whole of `CertifyRequest`.
  function submit(event: React.FormEvent) {
    event.preventDefault();
    void show(
      fetch(API + "/v1/certify", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Dev-Persona": persona },
        body: JSON.stringify({ dataset_id: datasetId }),
      }),
    );
  }

  // The narrow status wire a downstream consumer reads. It answers 404 until this persona's tenant
  // has certified the dataset, and 403 for a dataset certified only under another tenant.
  function readStatus() {
    void show(
      fetch(API + "/v1/certification/" + encodeURIComponent(datasetId), {
        cache: "no-store",
        headers: { "X-Dev-Persona": persona },
      }),
    );
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Certify a dataset. The scorecard is deterministic, cited, and routed to a human reviewer when it escalates."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The dataset</legend>
          <label>
            Dataset id (the local profile seeds the fictional datasets suggested here)
            <input
              list="seeded-datasets"
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
            />
            <datalist id="seeded-datasets">
              {SEEDED_DATASETS.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.note}
                </option>
              ))}
            </datalist>
          </label>
          <button type="submit" disabled={busy || !datasetId.trim()}>
            {busy ? "Working" : "Certify this dataset"}
          </button>{" "}
          <button type="button" disabled={busy || !datasetId.trim()} onClick={readStatus}>
            Read its certification status
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
