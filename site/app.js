// Buscador sobre ofertas.json (generado en cada ciclo por bot/exportar.py).
// Cada variante: { k: tokens, c: categoría, n: oferta nueva más barata, r: reacondicionada }
// Oferta: { t: título, s: tienda, p: precio, u: url, v: hora de comprobación (ISO) }
"use strict";

const MAX_RESULTADOS = 40;
const $ = (id) => document.getElementById(id);
let variantes = [];

const normalizar = (texto) =>
  texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const tokens = (texto) => normalizar(texto).match(/[a-z0-9]+/g) || [];

// Un término con números debe coincidir exacto ("s25" no encuentra "s250");
// uno solo de letras basta con que sea el comienzo de una palabra ("sams" → "samsung").
function coincide(terminos, conjunto, lista) {
  return terminos.every((t) =>
    /\d/.test(t) ? conjunto.has(t) : lista.some((p) => p.startsWith(t)));
}

function mejorOferta(v, incluirReac) {
  if (!incluirReac || !v.r) return v.n ? { ...v.n, reac: false } : null;
  if (!v.n || v.r.p < v.n.p) return { ...v.r, reac: true };
  return { ...v.n, reac: false };
}

const euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" });
const horaCorta = new Intl.DateTimeFormat("es-ES", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function haceCuanto(iso) {
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 1) return "ahora mismo";
  if (min < 60) return `hace ${min} min`;
  if (min < 48 * 60) return `hace ${Math.round(min / 60)} h`;
  return horaCorta.format(new Date(iso));
}

function pintar() {
  const consulta = $("q").value.trim();
  const incluirReac = $("reac").checked;
  const lista = $("resultados");
  lista.replaceChildren();
  try { history.replaceState(null, "", consulta ? `#${encodeURIComponent(consulta)}` : "#"); } catch {}

  if (!consulta) {
    $("estado").textContent = `${variantes.length} productos disponibles. Escribe qué buscas.`;
    return;
  }
  const terminos = tokens(consulta);
  const encontrados = [];
  for (const v of variantes) {
    if (!coincide(terminos, v._set, v._lista)) continue;
    const o = mejorOferta(v, incluirReac);
    if (o) encontrados.push(o);
  }
  encontrados.sort((a, b) => a.p - b.p);

  if (!encontrados.length) {
    $("estado").textContent = "Sin resultados. Prueba con menos palabras.";
    return;
  }
  const tpl = $("tpl").content;
  for (const o of encontrados.slice(0, MAX_RESULTADOS)) {
    const li = tpl.cloneNode(true);
    const a = li.querySelector(".titulo");
    a.textContent = o.t;
    a.href = o.u;
    li.querySelector(".precio").textContent = euros.format(o.p);
    li.querySelector(".tienda").textContent = o.s;
    const et = li.querySelector(".etiqueta");
    et.textContent = o.reac ? "Reacondicionado" : "Nuevo";
    if (o.reac) et.classList.add("reac");
    const hora = li.querySelector(".hora");
    hora.textContent = `Comprobado ${haceCuanto(o.v)}`;
    hora.title = new Date(o.v).toLocaleString("es-ES");
    lista.append(li);
  }
  const extra = encontrados.length > MAX_RESULTADOS ? ` (se muestran ${MAX_RESULTADOS})` : "";
  $("estado").textContent =
    `${encontrados.length} ${encontrados.length === 1 ? "variante" : "variantes"}, ` +
    `de la más barata a la más cara${extra}.`;
}

function pie(datos) {
  const caidas = (datos.tiendas || []).filter((t) => !t.ok).map((t) => t.tienda);
  $("pie").textContent =
    `Última actualización: ${horaCorta.format(new Date(datos.generado))}. ` +
    (caidas.length ? `Sin datos en este ciclo: ${caidas.join(", ")}.` : "Todas las tiendas respondieron.");
}

async function iniciar() {
  try {
    const r = await fetch("ofertas.json", { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const datos = await r.json();
    variantes = datos.variantes || [];
    for (const v of variantes) {
      v._lista = v.k.split(" ");
      v._set = new Set(v._lista);
    }
    pie(datos);
  } catch (e) {
    $("estado").textContent = `No se pudieron cargar las ofertas (${e.message}).`;
    return;
  }
  const inicial = decodeURIComponent(location.hash.slice(1));
  if (inicial) $("q").value = inicial;
  let espera;
  $("q").addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(pintar, 120); });
  $("reac").addEventListener("change", pintar);
  $("form").addEventListener("submit", (e) => { e.preventDefault(); pintar(); });
  pintar();
}

iniciar();
