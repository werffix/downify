const jobId = window.location.pathname.split("/").filter(Boolean).pop();
const loading = document.querySelector("#loading");
const loadingText = document.querySelector("#loading-text");
const releaseView = document.querySelector("#release");
const errorView = document.querySelector("#error");
const errorText = document.querySelector("#error-text");
const cover = document.querySelector("#cover");
const coverLink = document.querySelector("#cover-link");
const releaseTitle = document.querySelector("#release-title");
const releaseArtists = document.querySelector("#release-artists");
const zipLink = document.querySelector("#zip-link");
const singleTrack = document.querySelector("#single-track");
const tracklist = document.querySelector("#tracklist");

async function poll() {
  const response = await fetch(`/api/jobs/${jobId}`);
  const job = await response.json();

  if (!response.ok) {
    showError(job.detail || "Задача не найдена");
    return;
  }

  if (job.status === "error") {
    showError(job.error || job.message);
    return;
  }

  if (job.status !== "done") {
    loadingText.textContent = job.message || "Релиз скачивается на сервер";
    window.setTimeout(poll, 1200);
    return;
  }

  renderRelease(job);
}

function renderRelease(job) {
  loading.classList.add("hidden");
  releaseView.classList.remove("hidden");

  releaseTitle.textContent = job.title || "Release";
  releaseArtists.textContent = (job.artists || []).join(", ");

  if (job.has_cover) {
    cover.src = `/download/${jobId}/cover`;
    coverLink.href = `/download/${jobId}/cover`;
  } else {
    cover.remove();
    coverLink.remove();
  }

  if (job.has_zip) {
    zipLink.classList.remove("hidden");
    zipLink.href = `/download/${jobId}/zip`;
  }

  const tracks = job.tracks || [];
  if (job.kind === "track" && tracks[0] && tracks[0].path) {
    singleTrack.classList.remove("hidden");
    singleTrack.innerHTML = `<a class="primary-link" href="/download/${jobId}/tracks/0">Скачать трек</a>`;
  }

  tracklist.innerHTML = tracks.map((track, index) => trackRow(track, index)).join("");
}

function trackRow(track, index) {
  const artists = (track.artists || []).join(", ");
  const action = track.path
    ? `<a class="track-link" href="/download/${jobId}/tracks/${index}">Скачать</a>`
    : `<span class="track-error">${escapeHtml(track.error || "Не найдено")}</span>`;

  return `
    <article class="track-row">
      <div>
        <div class="track-title">${escapeHtml(track.title)}</div>
        <div class="track-artists">${escapeHtml(artists)}</div>
      </div>
      ${action}
    </article>
  `;
}

function showError(message) {
  loading.classList.add("hidden");
  releaseView.classList.add("hidden");
  errorView.classList.remove("hidden");
  errorText.textContent = message;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

poll();

