export function descriptionParts(text) {
  return text.split(/(\*\*[^*\r\n]+\*\*)/g).map((part, index) => ({
    strong: index % 2 === 1,
    text: index % 2 === 1 ? part.slice(2, -2) : part,
  })).filter((part) => part.text.length > 0);
}

export function renderDescription(element, text) {
  const document = element.ownerDocument;
  element.replaceChildren(...descriptionParts(text).map((part) => {
    if (!part.strong) return document.createTextNode(part.text);
    const strong = document.createElement("strong");
    strong.textContent = part.text;
    return strong;
  }));
}
