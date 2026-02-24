import { RouterProvider } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { TooltipProvider } from "@/components/ui/tooltip";
import { router } from "@/router";

function App() {
  return (
    <AuthProvider>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </AuthProvider>
  );
}

export default App;
