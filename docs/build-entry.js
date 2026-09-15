import React from "react";
import { createRoot } from "react-dom/client";
import htm from "htm";
import "./site.css";

globalThis.React = React;
globalThis.ReactDOM = { createRoot };
globalThis.htm = htm;

await import("./app.js");