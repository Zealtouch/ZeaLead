import packageJson from "../../package.json";

const currentYear = new Date().getFullYear();

export const APP_CONFIG = {
  name: "leadscout",
  version: packageJson.version,
  repo: "https://github.com/OWNER/leadscout",
  copyright: `© ${currentYear}, leadscout contributors.`,
  meta: {
    title: "leadscout — Autonomous Lead Discovery Console",
    description: "Console for the agent that finds people who need your product across public conversations",
  },
};
