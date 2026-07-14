interface CourseArchivePlaceholderProps {
  eyebrow: string
  title: string
  description: string
}

export function CourseArchivePlaceholder({
  eyebrow,
  title,
  description,
}: CourseArchivePlaceholderProps) {
  return (
    <section className="panel course-archive-placeholder">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  )
}
