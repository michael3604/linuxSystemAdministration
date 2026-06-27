export async function getJson(url) {
  const res = await fetch(url, {cache: 'no-store'});
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return await res.json();
}
export async function postJson(url, data) {
  const res = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return await res.json();
}
