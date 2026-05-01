const form = document.querySelector("#download-form");
const input = document.querySelector("#spotify-url");
const pasteButton = document.querySelector("#paste-button");
const statusText = document.querySelector("#status");

pasteButton.addEventListener("click", async () => {
  try {
    input.value = await navigator.clipboard.readText();
    input.focus();
  } catch {
    statusText.textContent = "Браузер не дал доступ к буферу обмена";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusText.textContent = "Релиз парсится и ставится в очередь";

  try {
    const response = await fetch("/api/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: input.value }),
    });

    if (!response.ok) {
      throw new Error("Не удалось создать задачу");
    }

    const data = await response.json();
    window.location.href = `/release/${data.job_id}`;
  } catch (error) {
    statusText.textContent = error.message;
  }
});

