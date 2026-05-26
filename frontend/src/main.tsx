/**
 * BizQuery — Entry point
 *
 * Bootstraps the React application and mounts it into the DOM.
 * AWS Amplify is configured here so it is available throughout the app.
 *
 * Requirements: 6.1, 6.4
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { configureAmplify } from "./config/amplify";
import App from "./App";

// Configure Amplify once before mounting the app
configureAmplify();

// ---------------------------------------------------------------------------
// Mount the application
// ---------------------------------------------------------------------------

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in the document.");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
