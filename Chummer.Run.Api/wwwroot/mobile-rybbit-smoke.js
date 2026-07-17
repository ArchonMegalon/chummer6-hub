(function () {
  if (typeof window === "undefined") {
    return;
  }

  if (window.rybbit && (typeof window.rybbit.track === "function" || typeof window.rybbit.event === "function")) {
    return;
  }

  window.rybbit = {
    track: function () {},
    event: function () {}
  };
})();
