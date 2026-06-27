export const $ = (id) => document.getElementById(id);
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
  children.forEach(c => node.append(c));
  return node;
}
