---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: QDash
  text: Qubit Calibration Platform
  tagline: Run calibration workflows, inspect results, and preserve their context
  image:
    src: /oqtopus_logo.svg
    alt: OQTOPUS
  actions:
    - theme: brand
      text: User Guide
      link: /user-guide/
    - theme: alt
      text: Developer Guide
      link: /developer-guide/
    - theme: alt
      text: Set Up QDash
      link: /user-guide/setup
    - theme: alt
      text: Watch the Demo
      link: /user-guide/what-is-qdash#demo

features:
  - title: Run Calibrations
    details: Create, schedule, and monitor workflows, or run an individual task from the workbench.
    link: /user-guide/running-calibrations
  - title: Inspect Calibration State
    details: Compare metrics, task results, artifacts, parameter history, and provenance for a chip.
    link: /user-guide/data-and-provenance
  - title: Collaborate on Results
    details: Connect notes, forum threads, knowledge, AI evaluations, and notifications.
    link: /user-guide/reviewing-results
  - title: Share by Project
    details: Keep workflows, calibration data, files, and membership within an explicit project boundary.
    link: /user-guide/projects-and-data-sharing
---
