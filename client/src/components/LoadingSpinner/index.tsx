import { InfinitySpin } from "react-loader-spinner";

export const LoadingSpinner = () => {
  return (
    <div className="loader-container">
      <InfinitySpin width="200" color="#4fa94d" />
    </div>
  );
};
