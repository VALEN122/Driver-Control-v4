import http from "node:http";
import OpenAI from "openai";

const port = Number(process.env.PORT || 8080);
const openAiKey = process.env.OPENAI_API_KEY;
const geminiKey = process.env.GEMINI_API_KEY;
const appToken = process.env.DRIVER_CONTROL_APP_TOKEN;
const openAiModel = process.env.OPENAI_MODEL || "gpt-6-astra";
const geminiModel = process.env.GEMINI_MODEL || "gemini-3.5-flash-lite";

if (!openAiKey && !geminiKey) {
  throw new Error("GEMINI_API_KEY or OPENAI_API_KEY is required");
}
if (!appToken) throw new Error("DRIVER_CONTROL_APP_TOKEN is required");

const openAiClient = openAiKey ? new OpenAI({ apiKey: openAiKey }) : null;
const requestWindows = new Map();
const rateWindowMs = 10 * 60 * 1000;
const rateLimit = 30;

const decisionSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    verdict: { type: "string", enum: ["ACEPTAR", "REVISAR", "RECHAZAR", "DETENERSE"] },
    score: { type: "integer", minimum: 0, maximum: 100 },
    answer: { type: "string" },
    reasons: {
      type: "array",
      minItems: 1,
      maxItems: 4,
      items: { type: "string" }
    },
    fatigue_advice: { type: "string" }
  },
  required: ["verdict", "score", "answer", "reasons", "fatigue_advice"]
};

const visionSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    detected: { type: "boolean" },
    confidence: { type: "number", minimum: 0, maximum: 1 },
    fare: { type: "number", minimum: 0 },
    pickup_min: { type: "number", minimum: 0 },
    pickup_km: { type: "number", minimum: 0 },
    trip_min: { type: "number", minimum: 0 },
    trip_km: { type: "number", minimum: 0 },
    destination: { type: "string" },
    note: { type: "string" }
  },
  required: [
    "detected", "confidence", "fare", "pickup_min", "pickup_km",
    "trip_min", "trip_km", "destination", "note"
  ]
};

const assistantInstructions = [
  "Sos el copiloto de seguridad y rentabilidad de Driver Control para un conductor humano.",
  "Respondé en español rioplatense, con frases breves y accionables.",
  "Evaluá tarifa, tiempo, kilómetros, combustible, objetivos, decisiones recientes y fatiga.",
  "La seguridad tiene prioridad: si la fatiga es alta, recomendá detenerse aunque el viaje sea rentable.",
  "Nunca afirmes que aceptaste o rechazaste el viaje. La decisión final siempre pertenece al conductor.",
  "No distraigas al conductor ni sugieras manipular el teléfono con el vehículo en movimiento."
].join(" ");

async function analyzeWithGemini(payload) {
  const endpoint =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(geminiModel)}:generateContent`;
  const geminiResponse = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": geminiKey
    },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: assistantInstructions }] },
      contents: [{ role: "user", parts: [{ text: JSON.stringify(payload) }] }],
      generationConfig: {
        responseMimeType: "application/json",
        responseJsonSchema: decisionSchema
      }
    })
  });

  if (!geminiResponse.ok) {
    const detail = (await geminiResponse.text()).slice(0, 1500);
    throw new Error(`gemini_${geminiResponse.status}: ${detail}`);
  }
  const data = await geminiResponse.json();
  const text = data?.candidates?.[0]?.content?.parts?.find(part => part.text)?.text;
  if (!text) throw new Error("gemini_empty_response");
  return JSON.parse(text);
}

async function readOfferImageWithGemini(payload) {
  const endpoint =
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(geminiModel)}:generateContent`;
  const prompt = [
    "Analizá esta captura de la app Uber Driver y extraé únicamente la oferta de viaje visible.",
    "Tarifa es el importe que gana el conductor; pickup es el tiempo/distancia para buscar al pasajero; trip es el viaje con el pasajero.",
    "Ignorá números del reloj, batería, mapa, Driver Control y otras aplicaciones.",
    "No inventes datos. Si no hay una oferta completa y legible, detected debe ser false y los números deben ser 0.",
    `OCR local auxiliar (puede contener errores): ${String(payload.local_text || "").slice(0, 2500)}`
  ].join(" ");
  const geminiResponse = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": geminiKey
    },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [
        { text: prompt },
        { inlineData: { mimeType: payload.mime_type, data: payload.image_base64 } }
      ] }],
      generationConfig: {
        responseMimeType: "application/json",
        responseJsonSchema: visionSchema,
        temperature: 0
      }
    })
  });
  if (!geminiResponse.ok) {
    const detail = (await geminiResponse.text()).slice(0, 1500);
    throw new Error(`gemini_vision_${geminiResponse.status}: ${detail}`);
  }
  const data = await geminiResponse.json();
  const text = data?.candidates?.[0]?.content?.parts?.find(part => part.text)?.text;
  if (!text) throw new Error("gemini_vision_empty_response");
  return JSON.parse(text);
}

async function analyzeWithOpenAI(payload) {
  const result = await openAiClient.responses.create({
    model: openAiModel,
    store: false,
    instructions: assistantInstructions,
    input: JSON.stringify(payload),
    text: {
      format: {
        type: "json_schema",
        name: "driver_trip_decision",
        strict: true,
        schema: decisionSchema
      }
    }
  });
  return JSON.parse(result.output_text);
}

function sendJson(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(JSON.stringify(body));
}

function readJson(request, maxLength = 64_000) {
  return new Promise((resolve, reject) => {
    let raw = "";
    request.on("data", chunk => {
      raw += chunk;
      if (raw.length > maxLength) {
        reject(new Error("request_too_large"));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        reject(new Error("invalid_json"));
      }
    });
    request.on("error", reject);
  });
}

function validateVisionPayload(payload) {
  if (payload?.mime_type !== "image/jpeg") throw new Error("invalid_image_type");
  if (typeof payload.image_base64 !== "string"
      || payload.image_base64.length < 1000
      || payload.image_base64.length > 2_000_000
      || !/^[A-Za-z0-9+/=]+$/.test(payload.image_base64)) {
    throw new Error("invalid_image");
  }
  return payload;
}

function validatePayload(payload) {
  const trip = payload?.trip;
  if (!trip || Number(trip.fare) <= 0 || Number(trip.total_min) <= 0 || Number(trip.total_km) <= 0) {
    throw new Error("invalid_trip");
  }
  return payload;
}

function isRateLimited(request) {
  const key = request.socket.remoteAddress || "unknown";
  const now = Date.now();
  const recent = (requestWindows.get(key) || []).filter(time => now - time < rateWindowMs);
  recent.push(now);
  requestWindows.set(key, recent);
  return recent.length > rateLimit;
}

const server = http.createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    return sendJson(response, 200, { ok: true, service: "driver-control-ai" });
  }

  const isAnalyze = request.method === "POST" && request.url === "/v1/driver/analyze";
  const isVision = request.method === "POST" && request.url === "/v1/driver/vision";
  if (!isAnalyze && !isVision) {
    return sendJson(response, 404, { error: "not_found" });
  }

  if (request.headers.authorization !== `Bearer ${appToken}`) {
    return sendJson(response, 401, { error: "unauthorized" });
  }
  if (isRateLimited(request)) {
    return sendJson(response, 429, { error: "rate_limited" });
  }

  try {
    let parsed;
    if (isVision) {
      if (!geminiKey) throw new Error("gemini_not_configured");
      const payload = validateVisionPayload(await readJson(request, 2_100_000));
      parsed = await readOfferImageWithGemini(payload);
    } else {
      const payload = validatePayload(await readJson(request));
      parsed = geminiKey
        ? await analyzeWithGemini(payload)
        : await analyzeWithOpenAI(payload);
    }
    return sendJson(response, 200, parsed);
  } catch (error) {
    console.error("driver_analysis_failed", error);
    const clientError = [
      "invalid_json", "invalid_trip", "invalid_image", "invalid_image_type", "request_too_large"
    ].includes(error.message);
    return sendJson(response, clientError ? 400 : 502, {
      error: clientError ? error.message : "ai_unavailable"
    });
  }
});

server.listen(port, () => {
  console.log(`Driver Control AI listening on port ${port}`);
});
