import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: 'Learn by phase',
    icon: '🍕',
    description: (
      <>
        Each phase starts with a request from Zé&apos;s Pizzeria and introduces
        the technology needed to answer it.
      </>
    ),
  },
  {
    title: 'Hands-on',
    icon: '🛠️',
    description: (
      <>
        Everything runs on your machine: the API, the database and the Docker
        stack. Follow along and feel the problems before reaching for tools.
      </>
    ),
  },
  {
    title: 'Decisions recorded',
    icon: '📝',
    description: (
      <>
        Architecture Decision Records explain why each important choice was
        made, so future contributors know the reasoning.
      </>
    ),
  },
];

function Feature({icon, title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        {/* Decorative: the heading below already says what the card is about. */}
        <span className={styles.featureIcon} aria-hidden="true">
          {icon}
        </span>
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
