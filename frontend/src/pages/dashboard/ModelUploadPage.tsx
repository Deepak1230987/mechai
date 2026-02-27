import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ModelVisibility } from "@/types";
import {
  requestUploadUrl,
  uploadFileToSignedUrl,
  confirmUpload,
} from "@/lib/models-api";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Upload, FileUp, X, Loader2, CheckCircle, Info } from "lucide-react";

const ACCEPTED_EXTENSIONS = [".step", ".stp", ".iges", ".igs", ".stl", ".x_t"];

/**
 * Map file extension to backend file_format enum value.
 */
function getFileFormat(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    step: "STEP",
    stp: "STEP",
    iges: "IGES",
    igs: "IGES",
    stl: "STL",
    x_t: "PARASOLID",
  };
  return map[ext] ?? "STEP";
}

type UploadStep =
  | "idle"
  | "requesting_url"
  | "uploading"
  | "confirming"
  | "done";

export function ModelUploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<ModelVisibility>("PRIVATE");
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState<UploadStep>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [stlWarning, setStlWarning] = useState(false);

  const validateFile = (f: File): boolean => {
    const ext = `.${f.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(
        `Invalid file type. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`,
      );
      setStlWarning(false);
      return false;
    }
    setError("");
    setStlWarning(ext === ".stl");
    return true;
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile && validateFile(droppedFile)) {
        setFile(droppedFile);
        if (!name) setName(droppedFile.name.replace(/\.[^.]+$/, ""));
      }
    },
    [name],
  );

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected && validateFile(selected)) {
      setFile(selected);
      if (!name) setName(selected.name.replace(/\.[^.]+$/, ""));
    }
  };

  const handleUpload = async () => {
    if (!file || !name) {
      setError("Please provide a file and model name");
      return;
    }

    setError("");

    try {
      // Step 1: Request signed upload URL
      setStep("requesting_url");
      const fileFormat = getFileFormat(file.name);
      const uploadRes = await requestUploadUrl(file.name, fileFormat, name);

      // Step 2: Upload file directly to signed URL
      setStep("uploading");
      setUploadProgress(0);
      await uploadFileToSignedUrl(uploadRes.signed_url, file, (percent) => {
        setUploadProgress(percent);
      });

      // Step 3: Confirm upload to trigger processing
      setStep("confirming");
      await confirmUpload(uploadRes.model_id);

      setStep("done");

      // Navigate to model detail after short delay to show success
      setTimeout(() => {
        navigate(`/models/${uploadRes.model_id}`);
      }, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setStep("idle");
    }
  };

  const removeFile = () => {
    setFile(null);
    setError("");
    setStep("idle");
    setUploadProgress(0);
    setStlWarning(false);
  };

  const isUploading = step !== "idle" && step !== "done";

  const stepLabels: Record<UploadStep, string> = {
    idle: "Upload Model",
    requesting_url: "Preparing upload...",
    uploading: `Uploading... ${uploadProgress}%`,
    confirming: "Confirming upload...",
    done: "Upload complete!",
  };

  return (
    <>
      <PageHeader
        title="Upload Model"
        description="Upload a CAD file to start the analysis process."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Drop zone */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base font-semibold">CAD File</CardTitle>
            <CardDescription>
              Supported formats: STEP, IGES, STL, Parasolid (.x_t)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!file ? (
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                className={`flex flex-col items-center justify-center rounded-lg border border-dashed p-10 text-center transition-colors ${
                  isDragOver
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/40"
                }`}
              >
                <Upload className="mb-4 h-10 w-10 text-muted-foreground/50" />
                <p className="mb-2 text-sm font-medium">
                  Drag & drop your CAD file here
                </p>
                <p className="mb-4 text-xs text-muted-foreground">
                  or click to browse
                </p>
                <label>
                  <Input
                    type="file"
                    className="hidden"
                    accept={ACCEPTED_EXTENSIONS.join(",")}
                    onChange={handleFileInput}
                  />
                  <Button variant="outline" size="sm" asChild>
                    <span>
                      <FileUp className="mr-2 h-4 w-4" />
                      Browse Files
                    </span>
                  </Button>
                </label>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between rounded-lg border border-border p-4">
                  <div className="flex items-center gap-3">
                    <FileUp className="h-8 w-8 text-primary" />
                    <div>
                      <p className="text-sm font-medium">{file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(file.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={removeFile}
                    disabled={isUploading}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {/* Upload progress bar */}
                {step === "uploading" && (
                  <div className="w-full bg-muted rounded-full h-1.5">
                    <div
                      className="bg-primary h-1.5 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                )}
              </div>
            )}

            {stlWarning && (
              <Alert className="mt-3 border-amber-500/30 bg-amber-500/5">
                <Info className="h-4 w-4 text-amber-600" />
                <AlertDescription className="text-sm text-muted-foreground">
                  STL supports viewing and RFQ only. Upload a STEP or IGES file
                  for full machining intelligence including feature detection
                  and automated plan generation.
                </AlertDescription>
              </Alert>
            )}

            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>

        {/* Model details */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Model Details
            </CardTitle>
            <CardDescription>
              Provide metadata for your CAD model.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="model-name" className="text-sm font-medium">
                Model Name
              </Label>
              <Input
                id="model-name"
                placeholder="e.g., Bracket Assembly v2"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isUploading}
                className="bg-input border-border"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="visibility" className="text-sm font-medium">
                Visibility
              </Label>
              <Select
                value={visibility}
                onValueChange={(v) => setVisibility(v as ModelVisibility)}
                disabled={isUploading}
              >
                <SelectTrigger className="bg-input border-border">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-border">
                  <SelectItem value="PRIVATE">Private</SelectItem>
                  <SelectItem value="PUBLIC">Public</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              className="w-full mt-4"
              disabled={!file || !name || isUploading || step === "done"}
              onClick={handleUpload}
            >
              {step === "done" ? (
                <>
                  <CheckCircle className="mr-2 h-4 w-4" />
                  {stepLabels[step]}
                </>
              ) : isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {stepLabels[step]}
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  {stepLabels[step]}
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
