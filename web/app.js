async function sendMsg() {
  const input = document.getElementById("msg");
  const msg = input.value.trim();
  if (!msg) return;

  const chatBox = document.getElementById("chat");
  chatBox.innerHTML += `<p><b>Tú:</b> ${msg}</p>`;
  input.value = "";

  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg })
  });

  const data = await resp.json();
  chatBox.innerHTML += `<p><b>Bot:</b> ${data.response}</p>`;
}
