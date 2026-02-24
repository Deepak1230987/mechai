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
import { Upload, FileUp, X, Loader2 } from "lucide-react";

const ACCEPTED_EXTENSIONS = [".step", ".stp", ".iges", ".igs", ".stl", ".x_t"];

export function ModelUploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<ModelVisibility>("PRIVATE");
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  const validateFile = (f: File): boolean => {
    const ext = `.${f.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(
        `Invalid file type. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`,
      );
      return false;
    }
    setError("");
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

    setIsUploading(true);

    // Simulate upload delay
    await new Promise((resolve) => setTimeout(resolve, 1500));

    setIsUploading(false);
    navigate("/models");
  };

  const removeFile = () => {
    setFile(null);
    setError("");
  };

  return (
    <>
      <PageHeader
        title="Upload Model"
        description="Upload a CAD file to start the analysis process."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Drop zone */}
        <Card>
          <CardHeader>
            <CardTitle>CAD File</CardTitle>
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
                className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
                  isDragOver
                    ? "border-primary bg-primary/5"
                    : "border-muted-foreground/25 hover:border-primary/50"
                }`}
              >
                <Upload className="mb-4 h-10 w-10 text-muted-foreground" />
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
              <div className="flex items-center justify-between rounded-lg border p-4">
                <div className="flex items-center gap-3">
                  <FileUp className="h-8 w-8 text-primary" />
                  <div>
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>
                <Button variant="ghost" size="icon" onClick={removeFile}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>

        {/* Model details */}
        <Card>
          <CardHeader>
            <CardTitle>Model Details</CardTitle>
            <CardDescription>
              Provide metadata for your CAD model.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="model-name">Model Name</Label>
              <Input
                id="model-name"
                placeholder="e.g., Bracket Assembly v2"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="visibility">Visibility</Label>
              <Select
                value={visibility}
                onValueChange={(v) => setVisibility(v as ModelVisibility)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PRIVATE">Private</SelectItem>
                  <SelectItem value="PUBLIC">Public</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button
              className="w-full mt-4"
              disabled={!file || !name || isUploading}
              onClick={handleUpload}
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload Model
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
