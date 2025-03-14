"use client";

import { Oval } from "react-loader-spinner";

export function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center h-full">
      <Oval
        height={80}
        width={80}
        color="#98A0F7"
        wrapperStyle={{}}
        wrapperClass=""
        visible={true}
        ariaLabel="oval-loading"
        secondaryColor="#98A0F7"
        strokeWidth={2}
        strokeWidthSecondary={2}
      />
    </div>
  );
}
