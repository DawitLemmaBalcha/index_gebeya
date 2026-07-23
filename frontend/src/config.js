// We use an empty string so requests go to the current domain (Relative Path).
// Example: fetch("/items") -> https://indexgebeya.cfd/items
// Apache then sees "/items" and forwards it to the Backend automatically.

export const API_BASE_URL = "";