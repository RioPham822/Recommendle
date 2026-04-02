import ImageOutlinedIcon from '@mui/icons-material/ImageOutlined';
import TuneRoundedIcon from '@mui/icons-material/TuneRounded';

export default function BrainModePanel({ mode, onModeChange, categoryCopy = {} }) {
  return (
    <div className="brain-mode-panel">
      <div className="brain-mode-panel__switch" role="tablist" aria-label="Display mode">
        <button
          type="button"
          className={`icon-button brain-mode-panel__button ${mode === 'visual' ? 'active' : ''}`}
          onClick={() => onModeChange('visual')}
          aria-label="Pictures mode"
          title="Pictures"
        >
          <ImageOutlinedIcon fontSize="small" />
        </button>
        <button
          type="button"
          className={`icon-button brain-mode-panel__button ${mode === 'feature' ? 'active' : ''}`}
          onClick={() => onModeChange('feature')}
          aria-label="Specifications mode"
          title="Specifications"
        >
          <TuneRoundedIcon fontSize="small" />
        </button>
      </div>
    </div>
  );
}
