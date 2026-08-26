"use client";

import { useEffect } from "react";

import { driver } from "driver.js";
import type { Config, DriveStep } from "driver.js";
import "driver.js/dist/driver.css";

interface ChipCreationTourProps {
  active: boolean;
  completed: boolean;
  restartKey: number;
  onDismiss: () => void;
}

const POPOVER_CLASS = "qdash-tour-popover";

export function getChipCreationTourSteps(): DriveStep[] {
  return [
    {
      popover: {
        title: "Create your first chip",
        description:
          "A chip identifies the device whose calibration data and task results QDash will track.",
      },
    },
    {
      element: '[data-tour="create-chip"]',
      advanceOnClick: true,
      popover: {
        title: "Open the chip form",
        description: "Select Create Chip to enter the device ID and topology.",
        side: "bottom",
        align: "end",
        showButtons: ["previous", "close"],
      },
    },
    {
      element: "#chip-id-input",
      waitForElement: 3000,
      popover: {
        title: "Name the chip",
        description: "Enter a unique ID used to identify this device across QDash.",
        side: "right",
        align: "start",
      },
    },
    {
      element: "#topology-select",
      waitForElement: 3000,
      popover: {
        title: "Choose a topology",
        description: "Select the template that matches the chip layout and number of qubits.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="submit-chip"]',
      waitForElement: 3000,
      popover: {
        title: "Create the chip",
        description: "Review the values, then select Create Chip to finish.",
        side: "top",
        align: "end",
        showButtons: ["previous", "close"],
      },
    },
  ];
}

function getTourConfig(onDismiss: () => void): Config {
  return {
    animate: true,
    smoothScroll: true,
    allowClose: true,
    allowScroll: true,
    disableActiveInteraction: false,
    showProgress: true,
    progressText: "{{current}} of {{total}}",
    nextBtnText: "Next",
    prevBtnText: "Back",
    doneBtnText: "Done",
    popoverClass: POPOVER_CLASS,
    stagePadding: 6,
    stageRadius: 10,
    onCloseClick: (_element, _step, { driver: tour }) => {
      tour.destroy();
      onDismiss();
    },
  };
}

export function ChipCreationTour({
  active,
  completed,
  restartKey,
  onDismiss,
}: ChipCreationTourProps) {
  useEffect(() => {
    if (!active) return;

    const tour = driver(getTourConfig(onDismiss));

    if (completed) {
      tour.setSteps([
        {
          popover: {
            title: "Chip created",
            description: "Your chip is ready. You can now select it and begin calibration work.",
            doneBtnText: "Finish",
            onDoneClick: (_element, _step, { driver: completedTour }) => {
              completedTour.destroy();
              onDismiss();
            },
          },
        },
      ]);
      tour.drive();
      return () => tour.destroy();
    }

    tour.setSteps(getChipCreationTourSteps());
    tour.drive(restartKey > 0 ? 1 : 0);

    return () => tour.destroy();
  }, [active, completed, onDismiss, restartKey]);

  return null;
}
