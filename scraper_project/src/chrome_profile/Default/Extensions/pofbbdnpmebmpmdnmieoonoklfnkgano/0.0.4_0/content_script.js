const subscribeBtn = document.getElementById("SubscribeItemBtn");
if (subscribeBtn) {
  const match = document.URL.toString().match(
    /steamcommunity\.com\/(?:workshop|sharedfiles)\/filedetails\/\?id=(\d+)/
  );
  if (match && match[1]) {
    const subscribeBtnText = document.getElementsByClassName(
      "subscribeText"
    )[0];
    subscribeBtnText.innerHTML = "Download";
    subscribeBtnText.addEventListener("click", (event) => {
      event.stopPropagation();
    });
    subscribeBtn.href = `http://steamworkshop.download/download/view/${match[1]}`;
    document
      .getElementsByClassName("game_area_purchase_game")[0]
      .getElementsByTagName("h1")[0]
      .getElementsByTagName("span")[0].style.display = "none";
    document
      .getElementsByClassName("game_area_purchase_game")[0]
      .getElementsByTagName("h1")[0]
      .getElementsByTagName("br")[0].style.display = "none";
  }
}
