"""
Audio Analysis Service
Speech-to-text, sentiment analysis, and voice confidence detection
"""
import speech_recognition as sr
import librosa
import numpy as np
from textblob import TextBlob
import soundfile as sf

def transcribe_audio(audio_filepath):
    """
    Convert speech to text using SpeechRecognition
    
    Args:
        audio_filepath: Path to audio file
    
    Returns:
        Transcribed text
    """
    recognizer = sr.Recognizer()
    
    # Try converting using librosa if direct read fails (often needed for WebM/Ogg)
    converted_path = None
    
    try:
        # First attempt: Direct read (fastest for WAV)
        with sr.AudioFile(audio_filepath) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
            
    except (ValueError, sr.UnknownValueError, Exception) as e:
        # Second attempt: Convert via librosa -> WAV
        try:
            print(f"Direct read failed ({e}), attempting conversion via librosa...")
            y, s_rate = librosa.load(audio_filepath, sr=None)
            
            # Save as temporary WAV
            converted_path = audio_filepath + ".converted.wav"
            sf.write(converted_path, y, s_rate)
            
            with sr.AudioFile(converted_path) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data)
                return text
                
        except Exception as conv_e:
            print(f"Transcription/Conversion error: {str(conv_e)}")
            return ""
        finally:
            # Cleanup converted file
            if converted_path and os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                except:
                    pass


def analyze_sentiment(text):
    """
    Analyze sentiment of text using TextBlob
    
    Args:
        text: Input text
    
    Returns:
        Sentiment score (-1 to 1)
    """
    if not text:
        return 0.0
    
    try:
        blob = TextBlob(text)
        # Polarity ranges from -1 (negative) to 1 (positive)
        return blob.sentiment.polarity
    except Exception as e:
        print(f"Sentiment analysis error: {str(e)}")
        return 0.0


def analyze_voice_features(audio_filepath):
    """
    Extract voice features for confidence analysis
    
    Args:
        audio_filepath: Path to audio file
    
    Returns:
        Dictionary with voice features
    """
    try:
        # Load audio file
        y, sr_rate = librosa.load(audio_filepath, sr=None)
        
        # Extract features
        
        # 1. Pitch (F0) - Higher variance may indicate nervousness
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr_rate)
        pitch_values = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:
                pitch_values.append(pitch)
        
        avg_pitch = np.mean(pitch_values) if pitch_values else 0
        pitch_variance = np.var(pitch_values) if pitch_values else 0
        
        # 2. Energy/Volume - Low energy may indicate low confidence
        rms = librosa.feature.rms(y=y)[0]
        avg_energy = np.mean(rms)
        
        # 3. Speaking rate (zero crossing rate as proxy)
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        avg_zcr = np.mean(zcr)
        
        # 4. Spectral features
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr_rate)[0]
        avg_spectral_centroid = np.mean(spectral_centroid)
        
        # 5. MFCC (Mel-frequency cepstral coefficients) - voice quality
        mfccs = librosa.feature.mfcc(y=y, sr=sr_rate, n_mfcc=13)
        avg_mfcc = np.mean(mfccs, axis=1)
        
        return {
            'avg_pitch': float(avg_pitch),
            'pitch_variance': float(pitch_variance),
            'avg_energy': float(avg_energy),
            'avg_zcr': float(avg_zcr),
            'avg_spectral_centroid': float(avg_spectral_centroid),
            'duration': len(y) / sr_rate
        }
    
    except Exception as e:
        print(f"Voice feature extraction error: {str(e)}")
        return {
            'avg_pitch': 0.0,
            'pitch_variance': 0.0,
            'avg_energy': 0.0,
            'avg_zcr': 0.0,
            'avg_spectral_centroid': 0.0,
            'duration': 0.0
        }


def calculate_confidence_score(voice_features):
    """
    Calculate confidence score from voice features
    
    Args:
        voice_features: Dictionary of extracted features
    
    Returns:
        Confidence score (0-1)
    """
    # Heuristic-based confidence scoring
    # Higher energy, moderate pitch variance, good duration = higher confidence
    
    score = 0.5  # Base score
    
    # Energy factor
    if voice_features['avg_energy'] > 0.02:
        score += 0.15
    elif voice_features['avg_energy'] > 0.01:
        score += 0.1
    
    # Pitch variance factor (moderate is good)
    if 100 < voice_features['pitch_variance'] < 5000:
        score += 0.15
    elif voice_features['pitch_variance'] > 0:
        score += 0.05
    
    # Duration factor (longer answers often show more confidence)
    if voice_features['duration'] > 30:
        score += 0.15
    elif voice_features['duration'] > 15:
        score += 0.1
    elif voice_features['duration'] > 5:
        score += 0.05
    
    # Speaking rate factor
    if 0.05 < voice_features['avg_zcr'] < 0.15:
        score += 0.05
    
    return max(0.0, min(1.0, score))  # Clamp between 0 and 1


def analyze_audio(audio_filepath, transcript=None):
    """
    Complete audio analysis pipeline
    
    Args:
        audio_filepath: Path to audio file
        transcript: Optional pre-computed transcript
    
    Returns:
        Dictionary with sentiment and confidence scores
    """
    # Get transcript if not provided
    if transcript is None:
        transcript = transcribe_audio(audio_filepath)
    
    # Analyze sentiment
    sentiment = analyze_sentiment(transcript)
    
    # Extract voice features
    voice_features = analyze_voice_features(audio_filepath)
    
    # Calculate confidence
    confidence = calculate_confidence_score(voice_features)
    
    return {
        'transcript': transcript,
        'sentiment': sentiment,
        'confidence': confidence,
        'voice_features': voice_features
    }
