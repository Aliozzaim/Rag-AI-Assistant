// Step 1: Import custom-elements polyfill FIRST (before Vue and Hades)
import "@ungap/custom-elements";

// Step 2: Import Hades styles CSS
import "@/hades-style/dist/styles.min.css";

// Step 3: Import Vue
import { createApp } from "vue";

// Step 4: Import Hades Vue plugin
import VueHDS from "@/hades-vue";

// Optional: Import Hades icons
import "@/hades-icons-vue3";

import App from "./App.vue";
import "./style.css";

// Step 5: Create app and register Hades plugin
const app = createApp(App);
app.use(VueHDS);
app.mount("#app");
