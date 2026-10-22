import { useEffect, useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { validateFiles } from '../../utils/validation'
import { FormMessage } from '../common/FormParts'
export function ImageUpload({
  files,
  onChange,
  error,
}: {
  files: File[]
  onChange: (files: File[]) => void
  error?: string
}) {
  const [previews, setPreviews] = useState<{ url: string; file: File }[]>([])
  const [selectionError, setSelectionError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    const next = files.map((file) => ({ file, url: URL.createObjectURL(file) }))
    void Promise.resolve().then(() => {
      if (active) setPreviews(next)
    })
    return () => {
      active = false
      next.forEach((item) => URL.revokeObjectURL(item.url))
    }
  }, [files])
  function choose(selected: File[]) {
    const chosen = [...files, ...selected]
    const problem = validateFiles(chosen)
    setSelectionError(problem ?? null)
    if (!problem) onChange(chosen)
  }
  return (
    <div>
      <label htmlFor="images" className="block text-sm font-medium text-slate-700">
        Photograph evidence (optional)
      </label>
      <p id="images-help" className="mb-3 mt-1 text-sm text-slate-600">
        Up to 2 JPEG, PNG, or WebP images, 1.5 MiB each. Maximum 4 megapixels and 4096px per
        dimension. Evidence is sanitized and stored privately on submission.
      </p>
      <div
        className="upload-dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          if (!event.currentTarget.closest('fieldset')?.disabled)
            choose(Array.from(event.dataTransfer.files))
        }}
      >
        <UploadCloud size={28} strokeWidth={1.5} aria-hidden="true" />
        <p>Drop photographs here, or choose files</p>
        <input
          className="block w-full text-sm"
          id="images"
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          aria-describedby="images-help"
          aria-invalid={Boolean(error || selectionError)}
          onChange={(event) => {
            choose(Array.from(event.target.files ?? []))
            event.target.value = ''
          }}
        />
        <span className="text-xs text-slate-500">
          Selected locally · Uploaded only when you submit
        </span>
      </div>
      <FormMessage error={selectionError ?? error} />
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {previews.map(({ file, url }, index) => (
          <figure className="min-w-0 rounded-xl border border-slate-200 p-2" key={url}>
            <img
              src={url}
              alt={`Selected evidence: ${file.name}`}
              className="h-28 w-full rounded-lg object-cover"
            />
            <figcaption className="mt-1 truncate text-xs">{file.name}</figcaption>
            <button
              type="button"
              className="mt-2 text-sm font-semibold text-red-700"
              aria-label={`Remove image ${index + 1}`}
              onClick={() => {
                onChange(files.filter((_, position) => position !== index))
                setSelectionError(null)
              }}
            >
              Remove
            </button>
          </figure>
        ))}
      </div>
    </div>
  )
}
