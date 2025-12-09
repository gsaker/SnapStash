'use client';

import { Card } from "./ui/card"
import { Button } from "./ui/button"
import { Slider } from "./ui/slider"
import { Play, Pause, Download, Volume2, SkipBack, SkipForward } from "lucide-react"
import { useState, useRef, useEffect } from "react"

interface EnhancedAudioPlayerProps {
  src: string
  isOwn: boolean
  fileName?: string
  fileSize?: number
  mimeType?: string
}

export function EnhancedAudioPlayer({ src, isOwn, fileName, fileSize, mimeType }: EnhancedAudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [totalDuration, setTotalDuration] = useState(0)
  const [isLoaded, setIsLoaded] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  const togglePlay = () => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause()
      } else {
        audioRef.current.play()
      }
      setIsPlaying(!isPlaying)
    }
  }

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setTotalDuration(audioRef.current.duration)
      setIsLoaded(true)
    }
  }

  const handleSeek = (value: number[]) => {
    const newTime = value[0]
    if (audioRef.current) {
      audioRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const skipForward = () => {
    if (audioRef.current) {
      const newTime = Math.min(audioRef.current.currentTime + 10, totalDuration)
      audioRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const skipBackward = () => {
    if (audioRef.current) {
      const newTime = Math.max(audioRef.current.currentTime - 10, 0)
      audioRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const formatTime = (time: number) => {
    const minutes = Math.floor(time / 60)
    const seconds = Math.floor(time % 60)
    return `${minutes}:${seconds.toString().padStart(2, "0")}`
  }

  const formatFileSize = (bytes: number | undefined) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const generateWaveform = () => {
    const bars = []
    for (let i = 0; i < 40; i++) {
      const height = Math.random() * 20 + 8
      const isActive = isLoaded && i / 40 <= currentTime / totalDuration
      bars.push(
        <div
          key={i}
          className={`w-1 rounded-full transition-all duration-150 ${
            isActive
              ? isOwn
                ? "bg-white"
                : "bg-blue-600"
              : isOwn
                ? "bg-white/30"
                : "bg-gray-300"
          }`}
          style={{ height: `${height}px` }}
        />
      )
    }
    return bars
  }

  return (
    <Card
      className={`p-4 border-0 shadow-sm min-w-80 ${
        isOwn ? "bg-yellow-500 text-white" : "bg-white text-gray-900"
      }`}
    >
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={() => setIsPlaying(false)}
        preload="metadata"
      />



      {/* Waveform Visualization */}
      <div className="flex items-center justify-center gap-0.5 mb-3 h-8">
        {generateWaveform()}
      </div>

      {/* Progress Slider */}
      <div className="mb-3">
        <Slider
          value={[currentTime]}
          max={totalDuration || 100}
          step={0.1}
          onValueChange={handleSeek}
          className="w-full"
          disabled={!isLoaded}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className={`rounded-full p-2 ${
              isOwn 
                ? "hover:bg-white/20 text-white" 
                : "hover:bg-gray-100 text-gray-600"
            }`}
            onClick={skipBackward}
            disabled={!isLoaded}
          >
            <SkipBack className="w-3 h-3" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className={`rounded-full p-2 ${
              isOwn 
                ? "hover:bg-white/20 text-white" 
                : "hover:bg-gray-100 text-gray-600"
            }`}
            onClick={togglePlay}
            disabled={!isLoaded}
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className={`rounded-full p-2 ${
              isOwn 
                ? "hover:bg-white/20 text-white" 
                : "hover:bg-gray-100 text-gray-600"
            }`}
            onClick={skipForward}
            disabled={!isLoaded}
          >
            <SkipForward className="w-3 h-3" />
          </Button>
          
          {/* Timer next to controls */}
          <div className="flex items-center gap-1 ml-2">
            <span className={`text-xs ${isOwn ? "text-white/80" : "text-gray-600"}`}>
              {isLoaded ? formatTime(currentTime) : "0:00"}
            </span>
            <span className={`text-xs ${isOwn ? "text-white/50" : "text-gray-400"}`}>
              /
            </span>
            <span className={`text-xs ${isOwn ? "text-white/80" : "text-gray-600"}`}>
              {isLoaded ? formatTime(totalDuration) : "0:00"}
            </span>
          </div>
        </div>

        <a
          href={src}
          download
          className={`p-2 rounded hover:bg-opacity-20 ${
            isOwn 
              ? "hover:bg-white text-white" 
              : "hover:bg-gray-100 text-gray-600"
          }`}
          title="Download"
        >
          <Download className="w-4 h-4" />
        </a>
      </div>
    </Card>
  )
}
