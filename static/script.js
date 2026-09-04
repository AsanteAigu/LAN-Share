/* LAN Share - self-hosted client script, no external dependencies */

(function () {
  "use strict";

  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("file-input");
  var progressContainer = document.getElementById("progress-container");
  var progressBar = document.getElementById("progress-bar");
  var progressText = document.getElementById("progress-text");
  var statusText = document.getElementById("upload-status");
  var fileList = document.getElementById("file-list");
  var fileCount = document.getElementById("file-count");

  var POLL_INTERVAL_MS = 4000;
  var statusTimer = null;

  function humanSizeFallback(bytes) {
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = 0;
    var n = bytes;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i++;
    }
    return (i === 0 ? Math.round(n) : n.toFixed(1)) + " " + units[i];
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderFiles(files) {
    fileCount.textContent = files.length
      ? files.length + (files.length === 1 ? " file" : " files")
      : "";

    if (!files.length) {
      fileList.innerHTML = '<li class="empty-state">No files shared yet.</li>';
      return;
    }

    var html = files.map(function (f) {
      var name = escapeHtml(f.name);
      var size = f.size || humanSizeFallback(f.size_bytes || 0);
      return (
        '<li class="file-item" data-filename="' + name + '">' +
          '<span class="file-name">' + name + "</span>" +
          '<span class="file-size">' + size + "</span>" +
          '<a class="btn-download" href="/download/' + encodeURIComponent(f.name) + '">Download</a>' +
          '<button type="button" class="btn-delete" data-filename="' + name + '">Delete</button>' +
        "</li>"
      );
    }).join("");

    fileList.innerHTML = html;
  }

  function fetchFiles() {
    fetch("/api/files")
      .then(function (res) { return res.json(); })
      .then(renderFiles)
      .catch(function () {
        /* silent fail on background poll - avoid spamming the user */
      });
  }

  function setStatus(msg, autoClearMs) {
    statusText.textContent = msg;
    if (statusTimer) {
      clearTimeout(statusTimer);
      statusTimer = null;
    }
    if (autoClearMs) {
      statusTimer = setTimeout(function () {
        statusText.textContent = "";
      }, autoClearMs);
    }
  }

  function uploadFiles(fileArray) {
    if (!fileArray.length) return;

    var formData = new FormData();
    fileArray.forEach(function (f) { formData.append("files", f); });

    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload");

    progressContainer.classList.remove("hidden");
    progressBar.style.width = "0%";
    progressText.textContent = "0%";
    setStatus("Uploading " + fileArray.length + (fileArray.length === 1 ? " file..." : " files..."));

    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = pct + "%";
        progressText.textContent = pct + "%";
      }
    };

    xhr.onload = function () {
      progressContainer.classList.add("hidden");
      if (xhr.status >= 200 && xhr.status < 300) {
        setStatus("Upload complete.", 4000);
      } else if (xhr.status === 413) {
        setStatus("One or more files exceed the max upload size.", 6000);
      } else {
        setStatus("Upload failed (status " + xhr.status + ").", 6000);
      }
      fetchFiles();
    };

    xhr.onerror = function () {
      progressContainer.classList.add("hidden");
      setStatus("Upload failed - connection error.", 6000);
    };

    xhr.send(formData);
  }

  dropzone.addEventListener("click", function () {
    fileInput.click();
  });

  dropzone.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", function () {
    uploadFiles(Array.prototype.slice.call(fileInput.files));
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", function (e) {
    var dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length) {
      uploadFiles(Array.prototype.slice.call(dt.files));
    }
  });

  fileList.addEventListener("click", function (e) {
    var btn = e.target.closest(".btn-delete");
    if (!btn) return;
    var filename = btn.getAttribute("data-filename");
    if (!window.confirm('Delete "' + filename + '"? This cannot be undone.')) return;

    fetch("/delete/" + encodeURIComponent(filename), { method: "POST" })
      .then(function (res) {
        if (!res.ok) throw new Error("Delete failed");
        return res.json();
      })
      .then(function () {
        setStatus('Deleted "' + filename + '".', 4000);
        fetchFiles();
      })
      .catch(function () {
        window.alert("Failed to delete file.");
      });
  });

  fetchFiles();
  setInterval(fetchFiles, POLL_INTERVAL_MS);
})();
