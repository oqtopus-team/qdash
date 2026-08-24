---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: QDash
  text: Qubit Calibration Platform
  tagline: Manage and monitor qubit calibration workflows with ease
  image:
    src: /oqtopus_logo.svg
    alt: OQTOPUS
  actions:
    - theme: brand
      text: Operator Guide
      link: /operator-guide/
    - theme: alt
      text: Developer Guide
      link: /developer-guide/
    - theme: alt
      text: Set Up QDash
      link: /operator-guide/setup

features:
  - title: Run Calibrations
    details: Create, schedule, and monitor project workflows or run an individual task from the workbench.
    link: /user-guide/running-calibrations
  - title: Inspect Calibration State
    details: Compare chip metrics, task results, raw artifacts, parameter history, and provenance.
    link: /user-guide/data-and-provenance
  - title: Collaborate on Results
    details: Connect notes, issues, forum discussions, knowledge cases, notifications, and AI reviews.
    link: /user-guide/reviewing-results
  - title: Share by Project
    details: Keep workflows, calibration data, files, and membership within an explicit project boundary.
    link: /user-guide/projects-and-sharing
---
