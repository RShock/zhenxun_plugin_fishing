// Artwork is a presentation layer; game_data.json remains the sole game data.
const base = new URL("./assets/", import.meta.url);

export function artwork(name, className = "s2-icon", alt = "") {
  if (!/^[a-z][a-z0-9_]*$/.test(name)) throw new Error("Invalid S2 artwork key");
  const image = document.createElement("img");
  image.src = new URL(`${name}.png`, base).href;
  image.className = className;
  image.alt = alt;
  image.width = 64; image.height = 64;
  image.decoding = "async";
  return image;
}

export function techArtwork(key) {
  return artwork(`tech_${key}`, "s2-tech-icon");
}

const markers = [
  ["🎉", "icon_celebrate"], ["🪐", "icon_core"], ["🌌", "icon_galaxy"],
  ["🔬", "icon_research"], ["✅", "icon_ready"], ["🚀", "icon_depart"],
];

export function illustratedNotice(text) {
  const row = document.createElement("div"); row.className = "s2-toast-row";
  const marker = markers.find(([prefix]) => text.startsWith(prefix));
  if (marker) {
    row.append(artwork(marker[1]));
    text = text.slice(marker[0].length).trimStart();
  }
  const label = document.createElement("span"); label.textContent = text;
  row.append(label);
  return row;
}
