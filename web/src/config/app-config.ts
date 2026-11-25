import packageJson from "../../package.json";

const currentYear = new Date().getFullYear();

export const APP_CONFIG = {
  name: "ZeaLead",
  version: packageJson.version,
  repo: "https://github.com/Zealtouch/ZeaLead",
  copyright: `© ${currentYear}, ZeaLead contributors.`,
  meta: {
    title: "ZeaLead — Autonomous Lead Discovery Console",
    description: "Console for the agent that finds people who need your product across public conversations",
  },
};
