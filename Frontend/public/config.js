window.AgriFusionDashboardConfig = {
  mode: "demo",
  resultPath: "result",
  defaultRange: "24h",
  firebase: {
    apiKey: "YOUR_FIREBASE_API_KEY",
    authDomain: "YOUR_PROJECT.firebaseapp.com",
    databaseURL: "https://YOUR_PROJECT-default-rtdb.REGION.firebasedatabase.app",
    projectId: "YOUR_PROJECT_ID",
    storageBucket: "YOUR_PROJECT.firebasestorage.app",
    messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
    appId: "YOUR_FIREBASE_APP_ID",
  },
};

window.AgriFusionDashboardConfigReady = (async () => {
  try {
    const response = await fetch("./config.local.json", { cache: "no-store" });
    if (!response.ok) {
      return window.AgriFusionDashboardConfig;
    }

    const localConfig = await response.json();
    window.AgriFusionDashboardConfig = mergeDashboardConfig(
      window.AgriFusionDashboardConfig,
      localConfig
    );
  } catch (_error) {
    // Local override is optional. Missing file keeps the dashboard in safe demo mode.
  }

  return window.AgriFusionDashboardConfig;
})();

function mergeDashboardConfig(baseConfig, overrideConfig) {
  if (!overrideConfig || typeof overrideConfig !== "object") {
    return baseConfig;
  }

  const overrideFirebase =
    overrideConfig.firebase && typeof overrideConfig.firebase === "object"
      ? overrideConfig.firebase
      : {};

  return {
    ...baseConfig,
    ...overrideConfig,
    firebase: {
      ...(baseConfig.firebase || {}),
      ...overrideFirebase,
    },
  };
}
