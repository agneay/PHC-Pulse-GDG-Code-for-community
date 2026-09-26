// Where is the user? Browser geolocation -> nearest reference town -> state -> regional language.
// Works offline: coordinates never leave the device (no reverse-geocoding service). Border areas
// resolve to the nearest listed town, so the result is a suggestion the user confirms, never forced.

// State -> [name, primary language, ...other widely spoken scheduled languages].
export const STATES = {
  AN: ['Andaman & Nicobar', 'hi', 'bn', 'ta'], AP: ['Andhra Pradesh', 'te', 'ur'], AR: ['Arunachal Pradesh', 'en', 'hi'],
  AS: ['Assam', 'as', 'brx', 'bn'], BR: ['Bihar', 'hi', 'mai', 'ur'], CH: ['Chandigarh', 'hi', 'pa'],
  CG: ['Chhattisgarh', 'hi'], DD: ['Dadra & Nagar Haveli and Daman & Diu', 'gu', 'mr'], DL: ['Delhi', 'hi', 'pa', 'ur'],
  GA: ['Goa', 'kok', 'mr'], GJ: ['Gujarat', 'gu', 'sd'], HR: ['Haryana', 'hi', 'pa'], HP: ['Himachal Pradesh', 'hi'],
  JK: ['Jammu & Kashmir', 'ur', 'ks', 'doi'], JH: ['Jharkhand', 'hi', 'sat', 'bn'], KA: ['Karnataka', 'kn', 'ur', 'kok'],
  KL: ['Kerala', 'ml'], LA: ['Ladakh', 'hi', 'ur'], LD: ['Lakshadweep', 'ml'], MP: ['Madhya Pradesh', 'hi'],
  MH: ['Maharashtra', 'mr', 'hi'], MN: ['Manipur', 'mni'], ML: ['Meghalaya', 'en'], MZ: ['Mizoram', 'en'],
  NL: ['Nagaland', 'en'], OD: ['Odisha', 'or', 'sat'], PY: ['Puducherry', 'ta', 'ml', 'te'], PB: ['Punjab', 'pa', 'hi'],
  RJ: ['Rajasthan', 'hi', 'sd'], SK: ['Sikkim', 'ne'], TN: ['Tamil Nadu', 'ta'], TG: ['Telangana', 'te', 'ur'],
  TR: ['Tripura', 'bn'], UP: ['Uttar Pradesh', 'hi', 'ur'], UK: ['Uttarakhand', 'hi', 'sa'], WB: ['West Bengal', 'bn', 'ne', 'sat'],
}

// [lat, lon, state]: capitals, district towns and border towns, dense enough that the nearest
// town is almost always in the right state.
const TOWNS = `13.08 80.27 TN|11.02 76.96 TN|9.93 78.12 TN|10.79 78.70 TN|11.66 78.15 TN|8.71 77.76 TN|12.92 79.13 TN|10.79 79.14 TN|11.94 79.49 TN|12.23 79.07 TN|8.08 77.54 TN|11.34 77.72 TN|12.13 78.16 TN|9.37 78.83 TN|11.41 76.70 TN|11.75 79.75 TN|12.52 78.21 TN|12.84 79.70 TN|10.36 77.98 TN|9.45 77.80 TN|12.74 77.83 TN|12.50 79.60 TN|10.96 79.38 TN|10.77 79.84 TN|
11.94 79.83 PY|
8.52 76.94 KL|9.93 76.27 KL|11.26 75.78 KL|10.53 76.21 KL|11.87 75.37 KL|10.79 76.65 KL|9.59 76.52 KL|9.85 76.97 KL|11.69 76.08 KL|12.50 75.00 KL|8.89 76.61 KL|9.27 76.79 KL|11.05 76.07 KL|
12.97 77.59 KA|12.30 76.64 KA|12.91 74.86 KA|15.36 75.12 KA|15.85 74.50 KA|17.33 76.83 KA|16.20 77.36 KA|15.14 76.92 KA|13.93 75.57 KA|14.46 75.92 KA|16.83 75.71 KA|17.91 77.52 KA|13.01 76.10 KA|14.23 76.40 KA|14.81 74.13 KA|13.14 78.13 KA|13.34 77.10 KA|11.92 76.94 KA|13.43 77.73 KA|15.43 75.63 KA|16.18 75.70 KA|12.52 76.90 KA|13.32 75.77 KA|16.77 77.14 KA|
15.49 73.83 GA|15.27 73.96 GA|
19.08 72.88 MH|18.52 73.86 MH|21.15 79.09 MH|20.00 73.79 MH|19.88 75.34 MH|17.66 75.91 MH|16.70 74.24 MH|20.93 77.75 MH|19.15 77.31 MH|18.40 76.56 MH|21.00 75.56 MH|16.99 73.30 MH|19.96 79.30 MH|20.70 77.00 MH|20.18 80.00 MH|19.27 76.77 MH|21.46 80.19 MH|20.39 78.13 MH|17.68 74.00 MH|
17.39 78.49 TG|17.97 79.59 TG|18.44 79.13 TG|18.67 78.09 TG|17.25 80.15 TG|16.74 78.00 TG|19.67 78.53 TG|17.05 79.27 TG|18.11 78.85 TG|17.61 78.08 TG|
17.69 83.22 AP|16.51 80.65 AP|16.31 80.44 AP|13.63 79.42 AP|14.44 79.99 AP|15.83 78.04 AP|14.68 77.60 AP|16.99 82.25 AP|17.00 81.80 AP|14.47 78.82 AP|18.30 83.90 AP|15.50 80.05 AP|13.22 79.10 AP|16.71 81.10 AP|18.11 83.40 AP|13.65 78.18 AP|15.48 78.48 AP|12.75 78.34 AP|13.20 78.75 AP|
20.30 85.82 OD|20.46 85.88 OD|22.26 84.85 OD|19.31 84.79 OD|21.47 83.97 OD|18.81 82.71 OD|19.17 83.42 OD|21.49 86.93 OD|18.86 82.57 OD|19.91 83.17 OD|21.63 85.58 OD|21.94 86.72 OD|18.35 81.89 OD|20.84 85.10 OD|20.70 83.48 OD|19.82 85.83 OD|20.47 86.49 OD|
21.25 81.63 CG|22.08 82.14 CG|19.08 82.02 CG|22.35 82.68 CG|23.12 83.20 CG|21.19 81.28 CG|18.90 81.35 CG|20.27 81.49 CG|22.02 81.23 CG|
23.26 77.41 MP|22.72 75.86 MP|23.18 79.99 MP|26.22 78.18 MP|23.18 75.78 MP|23.84 78.74 MP|24.53 81.30 MP|24.60 80.83 MP|22.06 78.94 MP|21.82 76.35 MP|23.30 81.36 MP|22.60 80.37 MP|24.47 74.87 MP|22.75 77.72 MP|24.64 77.30 MP|22.60 75.30 MP|25.67 78.46 MP|
23.02 72.57 GJ|21.17 72.83 GJ|22.31 73.18 GJ|22.30 70.80 GJ|23.25 69.67 GJ|22.47 70.06 GJ|21.76 72.15 GJ|21.52 70.46 GJ|23.22 72.65 GJ|24.17 72.43 GJ|20.61 72.93 GJ|22.84 74.26 GJ|20.40 72.83 DD|
26.91 75.79 RJ|26.24 73.02 RJ|24.59 73.71 RJ|25.21 75.86 RJ|28.02 73.31 RJ|26.45 74.64 RJ|26.92 70.91 RJ|25.75 71.39 RJ|29.90 73.88 RJ|27.55 76.60 RJ|27.22 77.49 RJ|23.55 74.44 RJ|28.30 74.95 RJ|24.88 74.63 RJ|25.18 76.12 RJ|27.61 75.14 RJ|
26.85 80.95 UP|26.45 80.33 UP|25.32 82.97 UP|27.18 78.01 UP|25.44 81.85 UP|26.76 83.37 UP|28.98 77.71 UP|28.37 79.43 UP|27.88 78.08 UP|25.45 78.57 UP|26.74 83.89 UP|26.80 82.20 UP|29.96 77.55 UP|28.84 78.77 UP|28.54 77.39 UP|28.67 77.45 UP|27.95 80.78 UP|27.57 81.60 UP|25.48 80.33 UP|25.15 82.57 UP|26.78 79.02 UP|26.07 83.18 UP|25.76 84.15 UP|24.69 83.07 UP|27.15 83.56 UP|
25.59 85.14 BR|24.79 85.00 BR|26.12 85.39 BR|25.24 86.98 BR|26.15 85.90 BR|25.78 87.47 BR|26.65 84.92 BR|25.56 84.66 BR|25.88 86.60 BR|24.95 84.03 BR|26.10 87.95 BR|26.22 84.36 BR|27.13 84.08 BR|
23.34 85.31 JH|22.80 86.20 JH|23.80 86.43 JH|23.67 86.15 JH|23.99 85.36 JH|24.48 86.70 JH|24.27 87.25 JH|24.03 84.07 JH|22.55 85.81 JH|24.19 86.30 JH|
22.57 88.36 WB|26.73 88.40 WB|23.52 87.31 WB|23.68 86.98 WB|23.23 87.86 WB|25.00 88.14 WB|22.35 87.23 WB|23.40 88.50 WB|26.32 89.45 WB|23.33 86.36 WB|23.23 87.07 WB|25.22 88.77 WB|22.03 88.06 WB|27.04 88.26 WB|24.10 88.27 WB|
28.61 77.21 DL|28.70 77.10 DL|
30.73 76.78 CH|28.46 77.03 HR|28.41 77.32 HR|29.15 75.72 HR|28.89 76.61 HR|30.38 76.78 HR|29.69 76.99 HR|29.53 75.03 HR|28.20 76.62 HR|29.39 76.97 HR|
30.90 75.85 PB|31.63 74.87 PB|31.33 75.58 PB|30.34 76.39 PB|30.21 74.95 PB|32.27 75.65 PB|30.93 74.61 PB|
31.10 77.17 HP|32.22 76.32 HP|31.71 76.93 HP|31.96 77.11 HP|30.90 77.10 HP|32.57 77.03 HP|
30.32 78.03 UK|29.95 78.16 UK|29.38 79.46 UK|29.22 79.51 UK|29.60 79.66 UK|29.58 80.21 UK|30.40 79.32 UK|30.73 78.44 UK|
34.08 74.80 JK|32.73 74.86 JK|33.73 75.15 JK|34.21 74.34 JK|32.37 75.52 JK|34.15 77.58 LA|34.56 76.13 LA|
26.14 91.74 AS|27.47 94.91 AS|24.83 92.78 AS|26.75 94.22 AS|26.63 92.80 AS|26.35 92.68 AS|26.02 89.98 AS|
25.58 91.89 ML|25.51 90.22 ML|27.08 93.61 AR|27.59 91.86 AR|28.07 95.33 AR|25.67 94.11 NL|25.91 93.73 NL|
24.82 93.94 MN|23.73 92.72 MZ|22.88 92.73 MZ|23.83 91.28 TR|27.33 88.61 SK|11.62 92.73 AN|10.57 72.64 LD`
  .split('|').map((s) => s.trim().split(' ')).map(([a, b, c]) => [Number(a), Number(b), c])

/** Nearest state for a coordinate, or null outside India. */
export function stateAt(lat, lon) {
  if (lat < 6 || lat > 37.5 || lon < 68 || lon > 97.5) return null
  const k = Math.cos((lat * Math.PI) / 180)
  let best = null
  for (const [a, b, st] of TOWNS) {
    const d = (a - lat) ** 2 + ((b - lon) * k) ** 2
    if (!best || d < best[0]) best = [d, st]
  }
  return best[1]
}

function position(timeout) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error('unsupported')); return }
    navigator.geolocation.getCurrentPosition(resolve, reject,
      { timeout, maximumAge: 24 * 3600 * 1000, enableHighAccuracy: false })
  })
}

/** { state, stateName, lang, source: 'location' | 'browser' } or null. */
export async function detectRegion(timeout = 8000) {
  try {
    const pos = await position(timeout)
    const st = stateAt(pos.coords.latitude, pos.coords.longitude)
    if (st) {
      const [stateName, lang, ...also] = STATES[st]
      return { state: st, stateName, lang, also, source: 'location' }
    }
  } catch { /* denied, unavailable or timed out: fall back to the browser's language list */ }
  const known = new Set(Object.values(STATES).flatMap(([, ...ls]) => ls))
  for (const tag of navigator.languages || [navigator.language]) {
    const base = (tag || '').toLowerCase().split('-')[0]
    if (base !== 'en' && known.has(base)) return { state: null, stateName: null, lang: base, also: [], source: 'browser' }
  }
  return null
}
